from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from db.models import (
    get_top_picks, get_upcoming_games, get_game_odds,
    insert_bet, get_pending_bets, get_bet_history,
    get_bet_stats, get_bet_stats_by_sport,
    get_top_prop_picks,
    get_kalshi_markets,
)
from engine.kalshi_edge import compute_kalshi_edges
from engine.calibration import get_calibration_summary
from engine.performance import (
    get_prediction_performance,
    get_daily_performance,
    get_edge_distribution,
    get_sport_comparison,
)
from config import config
import logging

logger = logging.getLogger("dashboard.routes")

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

PT = timezone(timedelta(hours=-7))  # PDT (UTC-7)


def _format_gametime(iso_str: str) -> str:
    """Convert ISO UTC string to readable Pacific time, e.g. 'Sat Mar 29, 6:40 PM'."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local = dt.astimezone(PT)
        return local.strftime("%a %b %d, %-I:%M %p PT")
    except Exception:
        return iso_str[:16]


templates.env.filters["gametime"] = _format_gametime


@router.get("/")
async def index(request: Request, sport: str = "", min_edge: float = 0.0):
    picks = get_top_picks(limit=50, min_edge=min_edge or config.alerts.min_edge, sport=sport)
    return templates.TemplateResponse("index.html", {
        "request": request,
        "picks": picks,
        "sport_filter": sport,
        "min_edge": min_edge,
        "sports": ["nfl", "nba", "mlb", "nhl", "soccer", "ufc"],
        "refresh_seconds": config.dashboard.refresh_seconds,
    })


@router.get("/games")
async def upcoming_games(request: Request, sport: str = ""):
    games = get_upcoming_games(hours=48)
    if sport:
        games = [g for g in games if g["sport"] == sport]
    return templates.TemplateResponse("games.html", {
        "request": request,
        "games": games,
        "sport_filter": sport,
        "sports": ["nfl", "nba", "mlb", "nhl", "soccer", "ufc"],
    })


@router.get("/calibration")
async def calibration(request: Request):
    summary = get_calibration_summary()
    return templates.TemplateResponse("calibration.html", {
        "request": request,
        "summary": summary,
    })


@router.get("/performance")
async def performance(request: Request):
    summary = get_prediction_performance()
    daily = get_daily_performance(days=30)
    edge_dist = get_edge_distribution()
    sport_cmp = get_sport_comparison()
    return templates.TemplateResponse("performance.html", {
        "request": request,
        "summary": summary,
        "daily": daily,
        "edge_dist": edge_dist,
        "sport_cmp": sport_cmp,
    })


@router.get("/roadmap")
async def roadmap(request: Request):
    return templates.TemplateResponse("roadmap.html", {"request": request})


@router.get("/api/picks")
async def api_picks(sport: str = "", min_edge: float = 0.0):
    picks = get_top_picks(limit=50, min_edge=min_edge or config.alerts.min_edge, sport=sport)
    return picks


@router.get("/api/game/{game_id}/odds")
async def api_game_odds(game_id: int):
    return get_game_odds(game_id)


@router.post("/bets/place")
async def place_bet(
    request: Request,
    prediction_id: int = Form(...),
    stake: float = Form(...),
):
    """Log a bet from the picks page. Looks up prediction to fill in all fields."""
    from db.database import get_connection as _gc
    conn = _gc()
    try:
        row = conn.execute(
            """
            SELECT p.game_id, p.selection, p.best_book, p.best_odds,
                   g.sport, g.home_team, g.away_team
            FROM predictions p
            JOIN games g ON p.game_id = g.id
            WHERE p.id = ?
            """,
            (prediction_id,),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        logger.warning(f"place_bet: prediction {prediction_id} not found")
        return RedirectResponse("/?error=prediction_not_found", status_code=303)

    # Resolve the display team name from selection key
    selection = row["selection"]
    if selection == "home":
        team_name = row["home_team"]
    elif selection == "away":
        team_name = row["away_team"]
    else:
        team_name = selection  # draw or literal name

    try:
        insert_bet(
            prediction_id=prediction_id,
            game_id=row["game_id"],
            sport=row["sport"],
            selection=team_name,
            bookmaker=row["best_book"] or "unknown",
            odds=int(row["best_odds"]),
            stake=stake,
        )
        logger.info(
            f"Bet logged: pred={prediction_id} team={team_name} "
            f"odds={row['best_odds']} stake=${stake}"
        )
    except Exception as e:
        logger.error(f"Failed to insert bet: {e}")

    return RedirectResponse("/?betlogged=1", status_code=303)


@router.get("/props")
async def props(request: Request, sport: str = "nba"):
    picks = get_top_prop_picks(sport=sport if sport != "all" else "", limit=50)
    return templates.TemplateResponse("props.html", {
        "request": request,
        "picks": picks,
        "sport_filter": sport,
        "sports": ["nba"],  # expandable as more sports are added
    })


@router.get("/api/props")
async def api_props(sport: str = "nba"):
    return get_top_prop_picks(sport=sport if sport != "all" else "", limit=50)


KALSHI_CATEGORIES = ["All", "Sports", "Politics", "Economics", "Crypto", "Climate", "Other"]


@router.get("/kalshi")
async def kalshi(request: Request, category: str = "All"):
    active_category = category if category in KALSHI_CATEGORIES else "All"
    cat_filter = "" if active_category == "All" else active_category

    markets = compute_kalshi_edges(category=cat_filter, limit=100)

    # Count per category for tab badges
    all_markets = get_kalshi_markets(category="", limit=2000)
    category_counts: dict[str, int] = {}
    for m in all_markets:
        c = m.get("category", "Other") or "Other"
        category_counts[c] = category_counts.get(c, 0) + 1

    total_markets = len(all_markets)

    # Last updated: newest updated_at across all markets
    last_updated = "Never"
    if all_markets:
        try:
            ts = max(m.get("updated_at", "") or "" for m in all_markets)
            if ts:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                last_updated = dt.astimezone(PT).strftime("%-I:%M %p PT")
        except Exception:
            pass

    return templates.TemplateResponse("kalshi.html", {
        "request": request,
        "markets": markets,
        "categories": KALSHI_CATEGORIES,
        "active_category": active_category,
        "category_counts": category_counts,
        "total_markets": total_markets,
        "last_updated": last_updated,
    })


@router.get("/api/kalshi")
async def api_kalshi(category: str = ""):
    return compute_kalshi_edges(category=category, limit=100)


@router.get("/tracker")
async def tracker(request: Request, sport: str = ""):
    stats = get_bet_stats(sport=sport)
    sport_breakdown = get_bet_stats_by_sport()
    history = get_bet_history(sport=sport, limit=50)
    pending = get_pending_bets()
    return templates.TemplateResponse("tracker.html", {
        "request": request,
        "stats": stats,
        "sport_breakdown": sport_breakdown,
        "history": history,
        "pending": pending,
        "sport_filter": sport,
        "sports": ["nfl", "nba", "mlb", "nhl", "soccer", "ufc"],
    })
