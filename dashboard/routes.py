from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from pathlib import Path
from db.models import get_top_picks, get_upcoming_games, get_game_odds
from config import config

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@router.get("/")
async def index(request: Request, sport: str = "", min_edge: float = 0.0):
    picks = get_top_picks(limit=50, min_edge=min_edge or config.alerts.min_edge)
    if sport:
        picks = [p for p in picks if p["sport"] == sport]
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


@router.get("/api/picks")
async def api_picks(sport: str = "", min_edge: float = 0.0):
    picks = get_top_picks(limit=50, min_edge=min_edge or config.alerts.min_edge)
    if sport:
        picks = [p for p in picks if p["sport"] == sport]
    return picks


@router.get("/api/game/{game_id}/odds")
async def api_game_odds(game_id: int):
    return get_game_odds(game_id)
