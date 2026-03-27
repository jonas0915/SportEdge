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


class Telegram:
    enabled: bool = _cfg["telegram"]["enabled"]
    bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")


class Config:
    odds_api = OddsAPI()
    alerts = Alerts()
    model = Model()
    kelly = Kelly()
    dashboard = Dashboard()
    telegram = Telegram()
    db_path: str = str(BASE_DIR / "sportedge.db")
    log_dir: str = str(BASE_DIR / "logs")


config = Config()
