import logging
from fetchers.odds_fetcher import OddsFetcher
from fetchers.stats_fetcher import StatsFetcher, get_team_stats, save_team_stats
from engine.value_finder import find_value_bets, find_value_bets_with_model
from engine.ranker import rank_predictions
from engine.elo import get_elo
from engine.probability import model_probability
from engine.rationale import generate_rationale
from db.models import upsert_game, insert_odds, insert_prediction, get_top_picks
from config import config

logger = logging.getLogger("engine.pipeline")

# Registry of sport modules
_sport_modules = {}

def _get_sport_module(sport: str):
    if not _sport_modules:
        from sports.nba import NBAModule
        from sports.mlb import MLBModule
        from sports.nfl import NFLModule
        from sports.nhl import NHLModule
        from sports.soccer import SoccerModule
        from sports.ufc import UFCModule
        _sport_modules["nba"] = NBAModule()
        _sport_modules["mlb"] = MLBModule()
        _sport_modules["nfl"] = NFLModule()
        _sport_modules["nhl"] = NHLModule()
        _sport_modules["soccer"] = SoccerModule()
        _sport_modules["ufc"] = UFCModule()
    return _sport_modules.get(sport)


async def run_stats_fetch():
    """Fetch and save team stats from ESPN. Called on separate schedule."""
    fetcher = StatsFetcher()
    try:
        count = await fetcher.fetch_all_sports()
        logger.info(f"Stats fetch complete: {count} teams updated")
    except Exception as e:
        logger.error(f"Stats fetch failed: {e}")
    finally:
        await fetcher.close()


async def run_pipeline() -> list[dict]:
    fetcher = OddsFetcher()
    try:
        games = await fetcher.fetch_all_active()
        logger.info(f"Fetched {len(games)} games across all sports")

        total_predictions = 0
        for game_data in games:
            game_id = upsert_game(
                sport=game_data["sport"],
                league=game_data["league"],
                home_team=game_data["home_team"],
                away_team=game_data["away_team"],
                start_time=game_data["start_time"],
                api_id=game_data["api_id"],
            )

            for o in game_data["odds"]:
                insert_odds(
                    game_id=game_id,
                    bookmaker=o["bookmaker"],
                    bet_type=o["bet_type"],
                    selection=o["selection"],
                    price=o["price"],
                    point=o.get("point"),
                )

            # Try model-based probability first
            sport_mod = _get_sport_module(game_data["sport"])
            home_stats = get_team_stats(game_data["sport"], game_data["home_team"])
            away_stats = get_team_stats(game_data["sport"], game_data["away_team"])

            if sport_mod and home_stats and away_stats:
                features = sport_mod.extract_features(home_stats, away_stats)
                home_elo = get_elo(game_data["sport"], game_data["home_team"])
                away_elo = get_elo(game_data["sport"], game_data["away_team"])
                model_prob = model_probability(
                    features, home_elo, away_elo, sport_mod.home_advantage
                )
                value_bets = find_value_bets_with_model(
                    game_data["odds"], model_prob, min_edge=config.alerts.min_edge
                )
                logger.debug(
                    f"Model prob for {game_data['home_team']} vs {game_data['away_team']}: "
                    f"{model_prob:.3f}"
                )
                _has_stats = True
                _home_elo_val = home_elo
                _away_elo_val = away_elo
            else:
                # Fallback to consensus-only (Phase 1 behavior)
                value_bets = find_value_bets(
                    game_data["odds"], min_edge=config.alerts.min_edge
                )
                _has_stats = False
                _home_elo_val = None
                _away_elo_val = None

            ranked = rank_predictions(value_bets)

            for pick in ranked:
                rationale = generate_rationale(
                    model_prob=pick["model_prob"],
                    market_prob=pick["market_prob"],
                    edge=pick["edge"],
                    selection=pick["selection"],
                    best_book=pick["best_book"],
                    best_odds=pick["best_odds"],
                    home_team=game_data["home_team"],
                    away_team=game_data["away_team"],
                    sport=game_data["sport"],
                    home_stats=home_stats if _has_stats else None,
                    away_stats=away_stats if _has_stats else None,
                    home_elo=_home_elo_val,
                    away_elo=_away_elo_val,
                )
                insert_prediction(
                    game_id=game_id,
                    bet_type=pick["bet_type"],
                    selection=pick["selection"],
                    model_prob=pick["model_prob"],
                    market_prob=pick["market_prob"],
                    edge=pick["edge"],
                    confidence=pick["confidence"],
                    kelly_fraction=pick["kelly_fraction"],
                    score=pick["score"],
                    rationale=rationale,
                    best_book=pick["best_book"],
                    best_odds=pick["best_odds"],
                )
                total_predictions += 1

        logger.info(f"Generated {total_predictions} predictions")
        return get_top_picks(limit=20, min_edge=config.alerts.min_edge)
    finally:
        await fetcher.close()
