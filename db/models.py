import sqlite3
from datetime import datetime, timezone
from db.database import get_connection


def upsert_game(
    sport: str,
    league: str,
    home_team: str,
    away_team: str,
    start_time: datetime,
    api_id: str,
) -> int:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id FROM games WHERE api_id = ?", (api_id,)
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE games SET start_time = ?, status = 'upcoming' WHERE id = ?",
                (start_time.isoformat(), row["id"]),
            )
            conn.commit()
            return row["id"]
        cursor = conn.execute(
            "INSERT INTO games (sport, league, home_team, away_team, start_time, api_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (sport, league, home_team, away_team, start_time.isoformat(), api_id),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def insert_odds(
    game_id: int,
    bookmaker: str,
    bet_type: str,
    selection: str,
    price: float,
    point: float | None = None,
):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO odds (game_id, bookmaker, bet_type, selection, price, point) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (game_id, bookmaker, bet_type, selection, price, point),
        )
        conn.commit()
    finally:
        conn.close()


def insert_prediction(
    game_id: int,
    bet_type: str,
    selection: str,
    model_prob: float,
    market_prob: float,
    edge: float,
    confidence: float,
    kelly_fraction: float,
    score: float,
    rationale: str,
    best_book: str,
    best_odds: float,
):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO predictions "
            "(game_id, bet_type, selection, model_prob, market_prob, edge, "
            "confidence, kelly_fraction, score, rationale, best_book, best_odds) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                game_id, bet_type, selection, model_prob, market_prob, edge,
                confidence, kelly_fraction, score, rationale, best_book, best_odds,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_top_picks(limit: int = 20, min_edge: float = 0.0, sport: str = "") -> list[dict]:
    conn = get_connection()
    try:
        if sport:
            rows = conn.execute(
                """
                SELECT p.*, g.sport, g.league, g.home_team, g.away_team, g.start_time
                FROM predictions p
                JOIN games g ON p.game_id = g.id
                WHERE g.status = 'upcoming' AND p.edge >= ? AND g.sport = ?
                ORDER BY p.score DESC
                LIMIT ?
                """,
                (min_edge, sport, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT p.*, g.sport, g.league, g.home_team, g.away_team, g.start_time
                FROM predictions p
                JOIN games g ON p.game_id = g.id
                WHERE g.status = 'upcoming' AND p.edge >= ?
                ORDER BY p.score DESC
                LIMIT ?
                """,
                (min_edge, limit),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_upcoming_games(hours: int = 48) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT g.*, GROUP_CONCAT(DISTINCT o.bookmaker) as bookmakers
            FROM games g
            LEFT JOIN odds o ON g.id = o.game_id
            WHERE g.status = 'upcoming'
              AND g.start_time <= datetime('now', '+' || ? || ' hours')
            GROUP BY g.id
            ORDER BY g.start_time ASC
            """,
            (hours,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_game_odds(game_id: int) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM odds
            WHERE game_id = ?
            ORDER BY timestamp DESC
            """,
            (game_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def insert_bet(
    prediction_id: int | None,
    game_id: int,
    sport: str,
    selection: str,
    bookmaker: str,
    odds: int,
    stake: float,
) -> int:
    """Log a new bet. Returns the new bet id."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO bets (prediction_id, game_id, sport, selection, bookmaker, odds, stake) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (prediction_id, game_id, sport, selection, bookmaker, int(odds), stake),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_pending_bets() -> list[dict]:
    """Return all bets where outcome IS NULL."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT b.*, g.home_team, g.away_team, g.start_time, g.winner, g.status as game_status
            FROM bets b
            JOIN games g ON b.game_id = g.id
            WHERE b.outcome IS NULL
            ORDER BY b.placed_at DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_bet_history(sport: str = "", limit: int = 50) -> list[dict]:
    """Return resolved bets, newest first."""
    conn = get_connection()
    try:
        if sport:
            rows = conn.execute(
                """
                SELECT b.*, g.home_team, g.away_team, g.start_time
                FROM bets b
                JOIN games g ON b.game_id = g.id
                WHERE b.outcome IS NOT NULL AND b.sport = ?
                ORDER BY b.resolved_at DESC
                LIMIT ?
                """,
                (sport, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT b.*, g.home_team, g.away_team, g.start_time
                FROM bets b
                JOIN games g ON b.game_id = g.id
                WHERE b.outcome IS NOT NULL
                ORDER BY b.resolved_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _compute_pnl(odds: int, stake: float, outcome: str) -> float:
    """Compute P&L from American odds, stake, and outcome."""
    if outcome == "win":
        if odds > 0:
            return stake * (odds / 100.0)
        else:
            return stake * (100.0 / abs(odds))
    elif outcome == "loss":
        return -stake
    else:  # push
        return 0.0


def resolve_bets() -> int:
    """
    Check all pending bets. If the game is final, compute P&L and set outcome.
    Returns the number of bets resolved.
    """
    conn = get_connection()
    try:
        pending = conn.execute(
            """
            SELECT b.id, b.odds, b.stake, b.selection,
                   g.winner, g.status as game_status, g.home_team, g.away_team
            FROM bets b
            JOIN games g ON b.game_id = g.id
            WHERE b.outcome IS NULL AND g.status = 'final'
            """
        ).fetchall()

        resolved = 0
        for row in pending:
            winner = row["winner"]
            selection = row["selection"]
            home_team = row["home_team"]
            away_team = row["away_team"]

            # Determine what team was picked
            if selection == "home":
                picked_team = home_team
            elif selection == "away":
                picked_team = away_team
            elif selection == "draw":
                picked_team = None  # push
            else:
                picked_team = selection  # Literal team name

            # Determine outcome
            if picked_team is None:
                outcome = "push"
            elif winner is None:
                # Draw/no winner — push
                outcome = "push"
            elif picked_team == winner:
                outcome = "win"
            else:
                outcome = "loss"

            pnl = _compute_pnl(row["odds"], row["stake"], outcome)

            conn.execute(
                """
                UPDATE bets
                SET outcome = ?, pnl = ?, resolved_at = datetime('now')
                WHERE id = ?
                """,
                (outcome, pnl, row["id"]),
            )
            resolved += 1

        if resolved > 0:
            conn.commit()

        return resolved
    finally:
        conn.close()


def get_bet_stats(sport: str = "") -> dict:
    """
    Return aggregate stats dict:
    total_bets, wins, losses, pushes, total_staked, total_pnl, roi_pct, win_rate
    """
    conn = get_connection()
    try:
        if sport:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) as total_bets,
                    SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) as losses,
                    SUM(CASE WHEN outcome = 'push' THEN 1 ELSE 0 END) as pushes,
                    SUM(stake) as total_staked,
                    SUM(COALESCE(pnl, 0)) as total_pnl
                FROM bets
                WHERE outcome IS NOT NULL AND sport = ?
                """,
                (sport,),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) as total_bets,
                    SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) as losses,
                    SUM(CASE WHEN outcome = 'push' THEN 1 ELSE 0 END) as pushes,
                    SUM(stake) as total_staked,
                    SUM(COALESCE(pnl, 0)) as total_pnl
                FROM bets
                WHERE outcome IS NOT NULL
                """
            ).fetchone()

        total_bets = row["total_bets"] or 0
        wins = row["wins"] or 0
        losses = row["losses"] or 0
        pushes = row["pushes"] or 0
        total_staked = row["total_staked"] or 0.0
        total_pnl = row["total_pnl"] or 0.0

        win_rate = (wins / (wins + losses)) * 100.0 if (wins + losses) > 0 else 0.0
        roi_pct = (total_pnl / total_staked) * 100.0 if total_staked > 0 else 0.0

        return {
            "total_bets": total_bets,
            "wins": wins,
            "losses": losses,
            "pushes": pushes,
            "total_staked": total_staked,
            "total_pnl": total_pnl,
            "roi_pct": roi_pct,
            "win_rate": win_rate,
        }
    finally:
        conn.close()


def get_bet_stats_by_sport() -> list[dict]:
    """Return per-sport bet stats for all sports that have resolved bets."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT
                sport,
                COUNT(*) as total_bets,
                SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN outcome = 'push' THEN 1 ELSE 0 END) as pushes,
                SUM(stake) as total_staked,
                SUM(COALESCE(pnl, 0)) as total_pnl
            FROM bets
            WHERE outcome IS NOT NULL
            GROUP BY sport
            ORDER BY total_bets DESC
            """
        ).fetchall()

        result = []
        for row in rows:
            wins = row["wins"] or 0
            losses = row["losses"] or 0
            total_staked = row["total_staked"] or 0.0
            total_pnl = row["total_pnl"] or 0.0
            win_rate = (wins / (wins + losses)) * 100.0 if (wins + losses) > 0 else 0.0
            roi_pct = (total_pnl / total_staked) * 100.0 if total_staked > 0 else 0.0
            result.append({
                "sport": row["sport"],
                "total_bets": row["total_bets"] or 0,
                "wins": wins,
                "losses": losses,
                "pushes": row["pushes"] or 0,
                "total_staked": total_staked,
                "total_pnl": total_pnl,
                "win_rate": win_rate,
                "roi_pct": roi_pct,
            })
        return result
    finally:
        conn.close()
