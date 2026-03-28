"""
Results fetcher — pulls completed game scores from The Odds API and resolves predictions.

Endpoint: GET /v4/sports/{sport_key}/scores/?apiKey={key}&daysFrom=2
Scores are free (0 credits). Runs every 30 minutes via scheduler.
"""
import logging
from datetime import datetime, timezone
from fetchers.base import BaseFetcher
from fetchers.odds_fetcher import SPORT_KEYS
from db.database import get_connection
from db.models import resolve_bets
from config import config

logger = logging.getLogger("engine.results")

# Map Odds API sport keys back to our internal sport names
API_KEY_TO_SPORT: dict[str, str] = {}
for _sport, _keys in SPORT_KEYS.items():
    for _key in _keys:
        API_KEY_TO_SPORT[_key] = _sport


def _update_game_final(
    conn,
    api_id: str,
    home_score: int | None,
    away_score: int | None,
    winner: str | None,
):
    """Mark a game as final and set scores/winner."""
    conn.execute(
        """
        UPDATE games
        SET status = 'final',
            home_score = ?,
            away_score = ?,
            winner = ?
        WHERE api_id = ?
        """,
        (home_score, away_score, winner, api_id),
    )


def _resolve_predictions_for_game(conn, game_id: int, winner: str | None):
    """
    Set outcome='win'/'loss' on all predictions for this game.
    prediction.selection is the team name (home_team or away_team string).
    """
    if winner is None:
        # Can't resolve without a winner (tie/draw in soccer — treat as 'push')
        conn.execute(
            "UPDATE predictions SET outcome = 'push' WHERE game_id = ? AND outcome IS NULL",
            (game_id,),
        )
        return

    rows = conn.execute(
        """
        SELECT p.id, p.selection, g.home_team, g.away_team
        FROM predictions p
        JOIN games g ON p.game_id = g.id
        WHERE p.game_id = ? AND p.outcome IS NULL
        """,
        (game_id,),
    ).fetchall()

    for row in rows:
        selection = row["selection"]
        home_team = row["home_team"]
        away_team = row["away_team"]

        # Resolve team name from selection key ('home', 'away', 'draw', or literal name)
        if selection == "home":
            picked_team = home_team
        elif selection == "away":
            picked_team = away_team
        elif selection == "draw":
            # Push — treat as loss for calibration purposes (no edge in a draw)
            conn.execute(
                "UPDATE predictions SET outcome = 'push' WHERE id = ?", (row["id"],)
            )
            continue
        else:
            picked_team = selection  # Literal team name

        outcome = "win" if picked_team == winner else "loss"
        conn.execute(
            "UPDATE predictions SET outcome = ? WHERE id = ?",
            (outcome, row["id"]),
        )


def _parse_score(scores_list: list[dict] | None, team_name: str) -> int | None:
    """Extract integer score for a given team from the scores array."""
    if not scores_list:
        return None
    for s in scores_list:
        if s.get("name") == team_name:
            try:
                return int(s["score"])
            except (KeyError, TypeError, ValueError):
                return None
    return None


def process_scores_response(data: list[dict], sport_key: str) -> tuple[int, int]:
    """
    Parse /scores response and update DB.
    Returns (games_updated, predictions_resolved).
    """
    games_updated = 0
    predictions_resolved = 0

    conn = get_connection()
    try:
        for event in data:
            if not event.get("completed", False):
                continue

            api_id = event.get("id")
            if not api_id:
                continue

            # Check we have this game in DB
            row = conn.execute(
                "SELECT id, status FROM games WHERE api_id = ?", (api_id,)
            ).fetchone()
            if not row:
                continue

            game_id = row["id"]

            # Skip if already finalized
            if row["status"] == "final":
                continue

            home_team = event.get("home_team")
            away_team = event.get("away_team")
            scores = event.get("scores")

            home_score = _parse_score(scores, home_team)
            away_score = _parse_score(scores, away_team)

            # Determine winner
            winner: str | None = None
            if home_score is not None and away_score is not None:
                if home_score > away_score:
                    winner = home_team
                elif away_score > home_score:
                    winner = away_team
                else:
                    winner = None  # Draw / push

            _update_game_final(conn, api_id, home_score, away_score, winner)
            games_updated += 1

            # Resolve predictions
            pending = conn.execute(
                "SELECT COUNT(*) as cnt FROM predictions WHERE game_id = ? AND outcome IS NULL",
                (game_id,),
            ).fetchone()["cnt"]

            if pending > 0:
                _resolve_predictions_for_game(conn, game_id, winner)
                predictions_resolved += pending

        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Error processing scores for {sport_key}: {e}")
        raise
    finally:
        conn.close()

    # Auto-resolve any tracked bets whose games are now final
    if games_updated > 0:
        try:
            bets_resolved = resolve_bets()
            if bets_resolved:
                logger.info(f"[{sport_key}] {bets_resolved} tracked bets resolved")
        except Exception as e:
            logger.error(f"Error resolving bets for {sport_key}: {e}")

    return games_updated, predictions_resolved


class ResultsFetcher(BaseFetcher):
    """Fetches game scores from The Odds API (free endpoint)."""

    async def fetch_scores(self, sport_key: str) -> list[dict]:
        """Fetch last 2 days of scores for a given Odds API sport key."""
        url = f"{config.odds_api.base_url}/sports/{sport_key}/scores/"
        params = {
            "apiKey": config.odds_api.key,
            "daysFrom": 2,
        }
        try:
            data = await self._request("GET", url, params=params)
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.warning(f"Failed to fetch scores for {sport_key}: {e}")
            return []

    async def fetch_and_resolve_all(self) -> dict:
        """
        Fetch scores for all sport keys and resolve predictions.
        Returns summary dict with totals.
        """
        total_games = 0
        total_predictions = 0
        errors = []

        for sport_key in API_KEY_TO_SPORT:
            try:
                data = await self.fetch_scores(sport_key)
                if not data:
                    continue

                games_updated, predictions_resolved = process_scores_response(
                    data, sport_key
                )
                if games_updated:
                    logger.info(
                        f"[{sport_key}] {games_updated} games finalized, "
                        f"{predictions_resolved} predictions resolved"
                    )
                total_games += games_updated
                total_predictions += predictions_resolved

            except Exception as e:
                logger.error(f"Results fetch failed for {sport_key}: {e}")
                errors.append(sport_key)

        return {
            "games_updated": total_games,
            "predictions_resolved": total_predictions,
            "errors": errors,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


async def run_results_fetch() -> dict:
    """Entry point called by scheduler."""
    fetcher = ResultsFetcher()
    try:
        result = await fetcher.fetch_and_resolve_all()
        logger.info(
            f"Results fetch complete: {result['games_updated']} games, "
            f"{result['predictions_resolved']} predictions resolved"
        )
        return result
    finally:
        await fetcher.close()
