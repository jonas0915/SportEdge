import logging
from config import config
from fetchers.base import BaseFetcher

logger = logging.getLogger("fetchers.kalshi")

# Kalshi sports series tickers to prioritize
SPORTS_SERIES = ["KXNBA", "KXNFL", "KXMLB", "KXNHL", "KXSB"]

# Category mapping: series prefix -> display category
SERIES_CATEGORY = {
    "KXNBA": "Sports",
    "KXNFL": "Sports",
    "KXMLB": "Sports",
    "KXNHL": "Sports",
    "KXSB": "Sports",
}

# Non-sports category keywords for classification
CATEGORY_KEYWORDS = {
    "Politics": ["president", "election", "senate", "house", "congress", "governor", "vote", "poll", "trump", "biden", "harris"],
    "Economics": ["fed", "rate", "gdp", "inflation", "recession", "unemployment", "cpi", "jobs", "market", "sp500", "nasdaq"],
    "Crypto": ["bitcoin", "btc", "ethereum", "eth", "crypto", "solana", "sol", "xrp"],
    "Climate": ["temperature", "hurricane", "tornado", "wildfire", "storm", "drought", "flood", "snow"],
    "Sports": ["nba", "nfl", "mlb", "nhl", "nba", "championship", "super bowl", "world series", "stanley cup"],
}


def _classify_category(ticker: str, title: str) -> str:
    """Classify a market into a category based on ticker prefix or title keywords."""
    ticker_upper = ticker.upper()
    for series in SPORTS_SERIES:
        if ticker_upper.startswith(series):
            return "Sports"

    title_lower = title.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in title_lower:
                return category

    return "Other"


def _parse_market(market: dict) -> dict | None:
    """Parse a single Kalshi market object into our internal format."""
    ticker = market.get("ticker") or market.get("market_ticker", "")
    if not ticker:
        return None

    # The market title may be in 'subtitle' (specific question) or 'title' (general)
    title = (
        market.get("subtitle")
        or market.get("title")
        or market.get("question")
        or ticker
    )

    event_ticker = market.get("event_ticker", "")

    # Prices: yes_bid / yes_ask give the bid-ask spread; midpoint = implied probability
    yes_bid = market.get("yes_bid", 0) or 0
    yes_ask = market.get("yes_ask", 0) or 0
    no_bid = market.get("no_bid", 0) or 0
    no_ask = market.get("no_ask", 0) or 0

    # Kalshi prices are in cents (0-100), convert to 0-1 probability
    if yes_bid or yes_ask:
        yes_mid_cents = (yes_bid + yes_ask) / 2.0
        yes_price = yes_mid_cents / 100.0
    else:
        # Fall back to last_price if bid/ask not available
        lp = market.get("last_price", 0) or 0
        yes_price = lp / 100.0 if lp > 1 else lp  # handle both formats

    if no_bid or no_ask:
        no_mid_cents = (no_bid + no_ask) / 2.0
        no_price = no_mid_cents / 100.0
    else:
        no_price = 1.0 - yes_price if yes_price else None

    # Volume / open interest — raw integers
    volume = market.get("volume", 0) or 0
    volume_24h = market.get("volume_24h", 0) or 0
    open_interest = market.get("open_interest", 0) or 0

    close_time = market.get("close_time") or market.get("expiration_time", "")
    status = market.get("status", "open")

    category = _classify_category(ticker, title)

    return {
        "ticker": ticker,
        "event_ticker": event_ticker,
        "title": title,
        "category": category,
        "status": status,
        "yes_price": yes_price,
        "no_price": no_price,
        "volume": int(volume),
        "volume_24h": int(volume_24h),
        "open_interest": int(open_interest),
        "close_time": close_time,
    }


class KalshiFetcher(BaseFetcher):
    """Fetches open markets from the Kalshi public API (no auth required for reads)."""

    def __init__(self):
        super().__init__()
        self._base_url = config.kalshi.base_url

    async def _fetch_markets_page(self, params: dict) -> tuple[list[dict], str | None]:
        """Fetch one page of markets. Returns (markets_list, next_cursor)."""
        url = f"{self._base_url}/markets"
        try:
            data = await self._request("GET", url, params=params)
        except Exception as e:
            logger.error(f"Kalshi API request failed: {e}")
            return [], None

        markets_raw = data.get("markets", [])
        cursor = data.get("cursor")  # next page cursor; None / empty when done
        return markets_raw, cursor or None

    async def fetch_sports_markets(self) -> list[dict]:
        """Fetch markets for each configured sports series."""
        results = []
        seen_tickers: set[str] = set()

        for series in config.kalshi.sports_series:
            cursor = None
            fetched = 0
            while True:
                params: dict = {
                    "status": "open",
                    "series_ticker": series,
                    "limit": 200,
                }
                if cursor:
                    params["cursor"] = cursor

                raw, cursor = await self._fetch_markets_page(params)
                if not raw:
                    break

                for m in raw:
                    parsed = _parse_market(m)
                    if parsed and parsed["ticker"] not in seen_tickers:
                        seen_tickers.add(parsed["ticker"])
                        results.append(parsed)
                        fetched += 1

                logger.debug(f"Kalshi sports series {series}: fetched page, {fetched} so far")

                if not cursor:
                    break  # no more pages

        logger.info(f"Kalshi: fetched {len(results)} sports markets")
        return results

    async def fetch_top_markets(self, limit: int = 200) -> list[dict]:
        """Fetch top open markets across all categories (sorted by volume)."""
        results = []
        seen_tickers: set[str] = set()
        cursor = None

        while len(results) < limit:
            params: dict = {
                "status": "open",
                "limit": min(200, limit - len(results)),
            }
            if cursor:
                params["cursor"] = cursor

            raw, cursor = await self._fetch_markets_page(params)
            if not raw:
                break

            for m in raw:
                parsed = _parse_market(m)
                if parsed and parsed["ticker"] not in seen_tickers:
                    seen_tickers.add(parsed["ticker"])
                    results.append(parsed)

            if not cursor:
                break

        logger.info(f"Kalshi: fetched {len(results)} top markets")
        return results

    async def fetch_all(self) -> list[dict]:
        """Fetch sports markets first, then fill with top non-sports markets."""
        from db.models import upsert_kalshi_market

        # 1. Sports markets (prioritized)
        sports = await self.fetch_sports_markets()
        sports_tickers = {m["ticker"] for m in sports}

        # 2. Top general markets — deduplicate against sports
        top = await self.fetch_top_markets(limit=300)
        non_sports = [m for m in top if m["ticker"] not in sports_tickers]

        all_markets = sports + non_sports
        logger.info(
            f"Kalshi: total {len(all_markets)} markets "
            f"({len(sports)} sports, {len(non_sports)} other)"
        )

        # 3. Upsert into DB
        saved = 0
        for m in all_markets:
            try:
                upsert_kalshi_market(
                    ticker=m["ticker"],
                    event_ticker=m["event_ticker"],
                    title=m["title"],
                    category=m["category"],
                    status=m["status"],
                    yes_price=m["yes_price"],
                    no_price=m["no_price"],
                    volume=m["volume"],
                    volume_24h=m["volume_24h"],
                    open_interest=m["open_interest"],
                    close_time=m["close_time"],
                )
                saved += 1
            except Exception as e:
                logger.warning(f"Failed to upsert Kalshi market {m['ticker']}: {e}")

        logger.info(f"Kalshi: saved/updated {saved} markets to DB")
        return all_markets
