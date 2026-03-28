import logging
from datetime import datetime, timezone, timedelta
from config import config
from fetchers.base import BaseFetcher
from fetchers.odds_fetcher import CreditBudget

logger = logging.getLogger("fetchers.props")

# DFS bookmaker keys in The Odds API
DFS_BOOKS = {"prizepicks", "underdog_fantasy"}

# Maps stat market key -> readable display name
STAT_DISPLAY = {
    "player_points": "Points",
    "player_rebounds": "Rebounds",
    "player_assists": "Assists",
    "player_threes": "3-Pointers Made",
}


def parse_props_response(data: dict, sport: str, game_id_map: dict) -> list[dict]:
    """
    Parse a single event's props response from The Odds API.
    Returns list of prop dicts with player_name, stat_type, line, bookmaker,
    over_price, under_price.
    """
    props = []
    event_id = data.get("id", "")
    game_id = game_id_map.get(event_id)

    for bk in data.get("bookmakers", []):
        bk_key = bk["key"]
        for market in bk.get("markets", []):
            stat_type = market["key"]
            if stat_type not in STAT_DISPLAY:
                continue

            # Each market has outcomes: one "Over" and one "Under" per player
            # Build player -> {over_price, under_price, line} map
            player_sides: dict[str, dict] = {}
            for outcome in market.get("outcomes", []):
                name = outcome.get("description") or outcome.get("name", "")
                if not name:
                    continue
                # The "name" field on player props is "Over" or "Under"
                # The "description" field is the player name
                # The "point" field is the line
                side = outcome.get("name", "").lower()  # "over" or "under"
                player_name = outcome.get("description", name)
                line = outcome.get("point")
                price = outcome.get("price")

                if line is None or price is None:
                    continue

                if player_name not in player_sides:
                    player_sides[player_name] = {"line": line}

                if side == "over":
                    player_sides[player_name]["over_price"] = price
                    player_sides[player_name]["line"] = line
                elif side == "under":
                    player_sides[player_name]["under_price"] = price

            for player_name, sides in player_sides.items():
                props.append({
                    "event_id": event_id,
                    "game_id": game_id,
                    "sport": sport,
                    "player_name": player_name,
                    "stat_type": stat_type,
                    "line": sides.get("line"),
                    "bookmaker": bk_key,
                    "over_price": sides.get("over_price"),
                    "under_price": sides.get("under_price"),
                })

    return props


class PropsFetcher(BaseFetcher):
    def __init__(self):
        super().__init__()
        self.budget = CreditBudget(config.odds_api.monthly_credit_budget)

    async def fetch_events(self, sport_key: str) -> list[dict]:
        """
        Fetch today's events using the FREE /events endpoint (0 credits).
        Returns events starting within the next 24 hours.
        """
        url = f"{config.odds_api.base_url}/sports/{sport_key}/events"
        params = {"apiKey": config.odds_api.key}
        try:
            events = await self._request("GET", url, params=params)
        except Exception as e:
            logger.error(f"Failed to fetch events for {sport_key}: {e}")
            return []

        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=24)
        upcoming = []
        for ev in events:
            try:
                commence = datetime.fromisoformat(
                    ev["commence_time"].replace("Z", "+00:00")
                )
                if now <= commence <= cutoff:
                    upcoming.append(ev)
            except Exception:
                continue

        logger.info(
            f"Events for {sport_key}: {len(events)} total, "
            f"{len(upcoming)} in next 24h"
        )
        return upcoming

    async def fetch_event_props(
        self,
        sport_key: str,
        event_id: str,
        markets: list[str],
    ) -> dict:
        """
        Fetch player props for a single event.
        Costs 1 credit per market per region.
        We use regions=us,us_dfs to get both sharp books and DFS platforms.
        """
        # Cost: len(markets) * 2 regions
        regions = ["us", "us2", "us_dfs"]
        credits_needed = len(markets) * len(regions)

        if not self.budget.can_spend(credits_needed):
            logger.warning(
                f"Credit budget exhausted — skipping props for event {event_id}"
            )
            return {}

        url = (
            f"{config.odds_api.base_url}/sports/{sport_key}"
            f"/events/{event_id}/odds"
        )
        params = {
            "apiKey": config.odds_api.key,
            "regions": ",".join(regions),
            "markets": ",".join(markets),
            "oddsFormat": "american",
        }
        try:
            data = await self._request("GET", url, params=params)
            self.budget.spend(credits_needed, sport=sport_key)
            return data
        except Exception as e:
            logger.error(f"Failed to fetch props for event {event_id}: {e}")
            return {}

    async def fetch_all_props(
        self,
        sport_key: str = "basketball_nba",
        markets: list[str] | None = None,
    ) -> list[dict]:
        """
        Fetch all player props for upcoming NBA games.
        Returns flat list of prop dicts.
        """
        if markets is None:
            markets = list(config.props.markets)

        sport = sport_key.split("_")[1] if "_" in sport_key else sport_key

        events = await self.fetch_events(sport_key)
        if not events:
            logger.info(f"No upcoming events for {sport_key} in next 24h")
            return []

        # Build event_id -> game_id map by looking up DB
        from db.database import get_connection
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT id, api_id FROM games WHERE sport = ?", (sport,)
            ).fetchall()
        finally:
            conn.close()
        game_id_map = {row["api_id"]: row["id"] for row in rows}

        all_props = []
        for event in events:
            event_id = event["id"]
            logger.info(
                f"Fetching props for event {event_id}: "
                f"{event.get('home_team')} vs {event.get('away_team')}"
            )
            raw = await self.fetch_event_props(sport_key, event_id, markets)
            if not raw:
                continue
            props = parse_props_response(raw, sport=sport, game_id_map=game_id_map)
            all_props.extend(props)
            logger.info(
                f"  Got {len(props)} prop lines from event {event_id}"
            )

        logger.info(
            f"Total prop lines fetched: {len(all_props)} | "
            f"Budget: {self.budget.spent_this_month}/{self.budget.monthly_limit} this month"
        )
        return all_props
