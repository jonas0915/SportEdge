from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from pathlib import Path
from db.models import get_top_picks, get_upcoming_games, get_game_odds
from engine.calibration import get_calibration_summary
from config import config

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
