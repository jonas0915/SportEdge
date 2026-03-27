import logging
from datetime import datetime, timezone, date
from config import config
from fetchers.base import BaseFetcher

logger = logging.getLogger("fetchers.odds")

SPORT_KEYS = {
    "nfl": ["americanfootball_nfl"],
    "nba": ["basketball_nba"],
    "mlb": ["baseball_mlb"],
    "nhl": ["icehockey_nhl"],
    "soccer": [
        "soccer_epl",
        "soccer_spain_la_liga",
        "soccer_italy_serie_a",
        "soccer_germany_bundesliga",
        "soccer_france_ligue_one",
        "soccer_uefa_champs_league",
    ],
    "ufc": ["mma_mixed_martial_arts"],
}

# Flat lookup for display names
LEAGUE_NAMES = {
    "soccer_epl": "Premier League",
    "soccer_spain_la_liga": "La Liga",
    "soccer_italy_serie_a": "Serie A",
    "soccer_germany_bundesliga": "Bundesliga",
    "soccer_france_ligue_one": "Ligue 1",
    "soccer_uefa_champs_league": "Champions League",
}


class CreditBudget:
    """Persistent credit tracker — survives restarts via SQLite."""

    def __init__(self, monthly_limit: int = 500):
        self.monthly_limit = monthly_limit

    @property
    def spent_today(self) -> int:
        from db.database import get_connection
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT COALESCE(SUM(credits), 0) as total FROM credit_log "
                "WHERE date(spent_at) = date('now')"
            ).fetchone()
            return row["total"]
        finally:
            conn.close()

    @property
    def spent_this_month(self) -> int:
        from db.database import get_connection
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT COALESCE(SUM(credits), 0) as total FROM credit_log "
                "WHERE strftime('%Y-%m', spent_at) = strftime('%Y-%m', 'now')"
            ).fetchone()
            return row["total"]
        finally:
            conn.close()

    def can_spend(self, credits: int) -> bool:
        return (self.spent_this_month + credits) <= self.monthly_limit

    def spend(self, credits: int, sport: str = ""):
        from db.database import get_connection
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO credit_log (credits, sport) VALUES (?, ?)",
                (credits, sport),
            )
            conn.commit()
        finally:
            conn.close()
        logger.info(
            f"Credits spent: {credits} ({sport}) | Today: {self.spent_today} | "
            f"Month: {self.spent_this_month}/{self.monthly_limit}"
        )


def parse_odds_response(data: list[dict], sport: str, league: str) -> list[dict]:
    games = []
    for event in data:
        odds_list = []
        home = event["home_team"]
        away = event["away_team"]
        for bk in event.get("bookmakers", []):
            for market in bk.get("markets", []):
                for outcome in market.get("outcomes", []):
                    if outcome["name"] == home:
                        selection = "home"
                    elif outcome["name"] == away:
                        selection = "away"
                    else:
                        selection = "draw"  # Soccer 3-way markets
                    odds_list.append({
                        "bookmaker": bk["key"],
                        "bet_type": market["key"],
                        "selection": selection,
                        "price": outcome["price"],
                        "point": outcome.get("point"),
                    })
        games.append({
            "api_id": event["id"],
            "sport": sport,
            "league": league,
            "home_team": home,
            "away_team": away,
            "start_time": datetime.fromisoformat(
                event["commence_time"].replace("Z", "+00:00")
            ),
            "odds": odds_list,
        })
    return games


class OddsFetcher(BaseFetcher):
    def __init__(self):
        super().__init__()
        self.budget = CreditBudget(config.odds_api.monthly_credit_budget)

    async def fetch_active_sports(self) -> set[str]:
        """Use the FREE /events endpoint to check which sports have upcoming games.
        This costs 0 credits — use it to gate paid odds fetches."""
        active = set()
        for sport, keys in SPORT_KEYS.items():
            for sport_key in keys:
                try:
                    url = f"{config.odds_api.base_url}/sports/{sport_key}/events"
                    params = {"apiKey": config.odds_api.key}
                    events = await self._request("GET", url, params=params)
                    if events:  # Has upcoming games
                        active.add(sport)
                        break  # One active key is enough to include the sport
                except Exception:
                    continue
        logger.info(f"Active sports with upcoming games: {active}")
        return active

    async def fetch_sport(self, sport: str) -> list[dict]:
        keys = SPORT_KEYS.get(sport)
        if not keys:
            logger.warning(f"Unknown sport: {sport}")
            return []

        all_games = []
        for sport_key in keys:
            credits_needed = len(config.odds_api.regions) * len(config.odds_api.markets)
            if not self.budget.can_spend(credits_needed):
                logger.warning("Credit budget exhausted, skipping fetch")
                break

            url = f"{config.odds_api.base_url}/sports/{sport_key}/odds"
            params = {
                "apiKey": config.odds_api.key,
                "regions": ",".join(config.odds_api.regions),
                "markets": ",".join(config.odds_api.markets),
                "oddsFormat": "american",
            }

            try:
                data = await self._request("GET", url, params=params)
                self.budget.spend(credits_needed, sport=sport_key)
                league = LEAGUE_NAMES.get(sport_key, sport)
                all_games.extend(parse_odds_response(data, sport=sport, league=league))
            except Exception as e:
                logger.error(f"Failed to fetch {sport_key}: {e}")
        return all_games

    async def fetch_all_active(self) -> list[dict]:
        # Step 1: Check which sports have games (FREE — 0 credits)
        active_sports = await self.fetch_active_sports()

        # Step 2: Only fetch odds for active sports (costs credits)
        all_games = []
        for sport in active_sports:
            try:
                games = await self.fetch_sport(sport)
                all_games.extend(games)
                logger.info(f"Fetched {len(games)} games for {sport}")
            except Exception as e:
                logger.error(f"Failed to fetch {sport}: {e}")
        logger.info(
            f"Total: {len(all_games)} games | Budget: "
            f"{self.budget.spent_today} credits today, "
            f"{self.budget.spent_this_month}/{self.budget.monthly_limit} this month"
        )
        return all_games
