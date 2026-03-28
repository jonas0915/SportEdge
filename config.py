import os
from pathlib import Path
from dotenv import load_dotenv
import yaml

load_dotenv()

BASE_DIR = Path(__file__).parent

with open(BASE_DIR / "config.yaml") as f:
    _cfg = yaml.safe_load(f)


class OddsAPI:
    key: str = os.getenv("ODDS_API_KEY", "")
    poll_interval_min: int = _cfg["odds_api"]["poll_interval_min"]
    lookahead_hours: int = _cfg["odds_api"]["lookahead_hours"]
    monthly_credit_budget: int = _cfg["odds_api"]["monthly_credit_budget"]
    regions: list[str] = _cfg["odds_api"]["regions"]
    markets: list[str] = _cfg["odds_api"]["markets"]
    base_url: str = "https://api.the-odds-api.com/v4"


class Alerts:
    score_threshold: float = _cfg["alerts"]["score_threshold"]
    min_edge: float = _cfg["alerts"]["min_edge"]
    pre_game_hours: int = _cfg["alerts"]["pre_game_hours"]
    min_alert_score: float = _cfg["alerts"]["min_alert_score"]


class Model:
    elo_weight: float = _cfg["model"]["elo_weight"]
    min_predictions_for_confidence: int = _cfg["model"]["min_predictions_for_confidence"]
    default_confidence: float = _cfg["model"]["default_confidence"]


class Kelly:
    fraction: float = _cfg["kelly"]["fraction"]
    max_stake_pct: float = _cfg["kelly"]["max_stake_pct"]


class Dashboard:
    port: int = _cfg["dashboard"]["port"]
    refresh_seconds: int = _cfg["dashboard"]["refresh_seconds"]
    timezone_display: str = _cfg["dashboard"]["timezone_display"]


class Props:
    enabled: bool = _cfg.get("props", {}).get("enabled", True)
    sports: list[str] = _cfg.get("props", {}).get("sports", ["basketball_nba"])
    markets: list[str] = _cfg.get("props", {}).get(
        "markets",
        ["player_points", "player_rebounds", "player_assists", "player_threes"],
    )
    min_edge: float = _cfg.get("props", {}).get("min_edge", 0.05)
    poll_interval_min: int = _cfg.get("props", {}).get("poll_interval_min", 60)


class Telegram:
    enabled: bool = _cfg["telegram"]["enabled"]
    bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    min_alert_score: float = _cfg["telegram"]["min_alert_score"]


class Kalshi:
    enabled: bool = _cfg.get("kalshi", {}).get("enabled", True)
    base_url: str = _cfg.get("kalshi", {}).get(
        "base_url", "https://api.elections.kalshi.com/trade-api/v2"
    )
    poll_interval_min: int = _cfg.get("kalshi", {}).get("poll_interval_min", 30)
    sports_series: list[str] = _cfg.get("kalshi", {}).get(
        "sports_series", ["KXNBA", "KXNFL", "KXMLB", "KXNHL", "KXSB"]
    )


class Config:
    odds_api = OddsAPI()
    alerts = Alerts()
    model = Model()
    kelly = Kelly()
    dashboard = Dashboard()
    telegram = Telegram()
    props = Props()
    kalshi = Kalshi()
    db_path: str = str(BASE_DIR / "sportedge.db")
    log_dir: str = str(BASE_DIR / "logs")


config = Config()
