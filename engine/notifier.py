"""
SportEdge Telegram notifier.
Sends top-pick alerts via Telegram Bot API using HTML formatting.
"""

import logging
from datetime import datetime, timezone, timedelta

import httpx

from config import config
from db.models import get_top_picks

logger = logging.getLogger("engine.notifier")

PT = timezone(timedelta(hours=-7))  # PDT (UTC-7)

# Sport display labels and emojis
_SPORT_EMOJI = {
    "nba": "🏀",
    "nfl": "🏈",
    "mlb": "⚾",
    "nhl": "🏒",
    "soccer": "⚽",
    "ufc": "🥊",
}

# In-memory set of prediction IDs already sent this session — prevents duplicates
_sent_ids: set[int] = set()


class TelegramNotifier:
    """Thin wrapper around the Telegram Bot API sendMessage endpoint."""

    def __init__(self):
        self.token: str = config.telegram.bot_token
        self.chat_id: str = config.telegram.chat_id
        self._base_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    def is_configured(self) -> bool:
        """Return True only when both token and chat_id are non-empty."""
        return bool(self.token and self.chat_id)

    async def send_message(self, text: str) -> bool:
        """
        Send a message to the configured chat.
        Returns True on success, False on any failure.
        Never raises — failures are logged as warnings.
        """
        if not self.is_configured():
            logger.info("Telegram not configured — skipping send_message")
            return False

        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(self._base_url, json=payload)
                if resp.status_code == 200 and resp.json().get("ok"):
                    logger.info("Telegram message sent successfully")
                    return True
                else:
                    logger.warning(
                        f"Telegram API error {resp.status_code}: {resp.text[:200]}"
                    )
                    return False
        except httpx.TimeoutException:
            logger.warning("Telegram send_message timed out")
            return False
        except Exception as e:
            logger.warning(f"Telegram send_message failed: {e}")
            return False


def _format_american_odds(odds: float) -> str:
    """Return odds as '+145' or '-110' string."""
    if odds >= 0:
        return f"+{int(odds)}"
    return str(int(odds))


def _format_gametime(iso_str: str) -> str:
    """Convert ISO UTC string to short Pacific time, e.g. 'Sat Mar 29 6:40 PM PT'."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local = dt.astimezone(PT)
        return local.strftime("%a %b %d %-I:%M %p PT")
    except Exception:
        return iso_str[:16]


def _build_alert_message(picks: list[dict]) -> str:
    """
    Build an HTML-formatted Telegram message for the given picks.

    Example output:
        🏀 SportEdge Alert — 3 Value Bets Found

        1. Bet <b>Lakers ML</b> (+145 @ DraftKings)
           Edge: +11.2% | Model: 62% vs Market: 51%
           🕐 Sat Mar 29 7:30 PM PT
        ...
    """
    n = len(picks)
    # Pick dominant sport emoji for header (most common sport in the list)
    sport_counts: dict[str, int] = {}
    for p in picks:
        s = p.get("sport", "")
        sport_counts[s] = sport_counts.get(s, 0) + 1
    top_sport = max(sport_counts, key=sport_counts.get) if sport_counts else ""
    header_emoji = _SPORT_EMOJI.get(top_sport, "🎯")

    lines = [
        f"{header_emoji} <b>SportEdge Alert — {n} Value Bet{'s' if n != 1 else ''} Found</b>",
        "",
    ]

    for i, pick in enumerate(picks, start=1):
        sport = pick.get("sport", "")
        sport_emoji = _SPORT_EMOJI.get(sport, "🎯")

        selection = pick.get("selection", "?")
        bet_type = pick.get("bet_type", "ML")
        best_book = pick.get("best_book", "?")
        best_odds = pick.get("best_odds", 0)
        edge = pick.get("edge", 0.0)
        model_prob = pick.get("model_prob", 0.0)
        market_prob = pick.get("market_prob", 0.0)
        start_time = pick.get("start_time", "")

        odds_str = _format_american_odds(best_odds)
        edge_pct = f"+{edge * 100:.1f}%"
        model_pct = f"{model_prob * 100:.0f}%"
        market_pct = f"{market_prob * 100:.0f}%"

        gametime = _format_gametime(start_time) if start_time else ""

        lines.append(
            f"{i}. {sport_emoji} Bet <b>{selection} {bet_type}</b> "
            f"({odds_str} @ {best_book})"
        )
        lines.append(
            f"   Edge: {edge_pct} | Model: {model_pct} vs Market: {market_pct}"
        )
        if gametime:
            lines.append(f"   🕐 {gametime}")
        lines.append("")

    # Trim trailing blank line
    while lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)


async def send_top_picks_alert(
    min_score: float | None = None,
    limit: int = 5,
) -> bool:
    """
    Fetch top picks from the DB and send a Telegram alert if any qualify.

    Args:
        min_score: Minimum score threshold. Defaults to config.alerts.min_alert_score.
        limit: Maximum number of picks to include in the alert.

    Returns:
        True if a message was sent, False otherwise.
    """
    notifier = TelegramNotifier()

    if not notifier.is_configured():
        logger.info("Telegram not configured — skipping top-picks alert")
        return False

    if not config.telegram.enabled:
        logger.info("Telegram alerts disabled in config — skipping")
        return False

    # Resolve score threshold
    threshold = min_score if min_score is not None else config.alerts.min_alert_score

    # Pull top picks from DB, filtering by the existing min_edge config
    all_picks = get_top_picks(limit=100, min_edge=config.alerts.min_edge)

    # Apply score threshold
    qualified = [p for p in all_picks if p.get("score", 0) >= threshold]

    if not qualified:
        logger.info(
            f"No picks above score threshold {threshold:.4f} — skipping alert"
        )
        return False

    # Filter out picks already sent this session
    new_picks = [p for p in qualified if p.get("id") not in _sent_ids]

    if not new_picks:
        logger.info("All qualified picks already alerted — skipping duplicate")
        return False

    # Take top N
    to_alert = new_picks[:limit]

    message = _build_alert_message(to_alert)

    # Log the formatted message so we can verify it looks correct
    logger.info(f"Sending Telegram alert:\n{message}")

    success = await notifier.send_message(message)

    if success:
        # Mark these IDs as sent
        for p in to_alert:
            pid = p.get("id")
            if pid is not None:
                _sent_ids.add(pid)

    return success


# ---------------------------------------------------------------------------
# Preview helper — call directly to see what an alert looks like
# ---------------------------------------------------------------------------

def preview_alert(picks: list[dict] | None = None) -> str:
    """
    Return a formatted alert string for preview/testing.
    If no picks provided, generates sample data.
    """
    if picks is None:
        picks = [
            {
                "id": 1,
                "sport": "nba",
                "selection": "Lakers ML",
                "bet_type": "h2h",
                "best_book": "DraftKings",
                "best_odds": 145.0,
                "edge": 0.112,
                "model_prob": 0.62,
                "market_prob": 0.51,
                "score": 0.085,
                "start_time": "2026-03-28T02:00:00",
            },
            {
                "id": 2,
                "sport": "ufc",
                "selection": "Niko Price ML",
                "bet_type": "h2h",
                "best_book": "BetOnline",
                "best_odds": 550.0,
                "edge": 0.324,
                "model_prob": 0.47,
                "market_prob": 0.154,
                "score": 0.061,
                "start_time": "2026-03-29T00:00:00",
            },
            {
                "id": 3,
                "sport": "mlb",
                "selection": "Yankees ML",
                "bet_type": "h2h",
                "best_book": "FanDuel",
                "best_odds": -120.0,
                "edge": 0.073,
                "model_prob": 0.58,
                "market_prob": 0.545,
                "score": 0.021,
                "start_time": "2026-03-28T23:10:00",
            },
        ]
    return _build_alert_message(picks)


if __name__ == "__main__":
    # Quick preview — run: python -m engine.notifier
    print(preview_alert())
