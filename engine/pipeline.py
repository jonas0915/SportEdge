import logging
from fetchers.odds_fetcher import OddsFetcher
from engine.value_finder import find_value_bets
from engine.ranker import rank_predictions
from db.models import upsert_game, insert_odds, insert_prediction, get_top_picks
from config import config

logger = logging.getLogger("engine.pipeline")


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

            value_bets = find_value_bets(
                game_data["odds"], min_edge=config.alerts.min_edge
            )
            ranked = rank_predictions(value_bets)

            for pick in ranked:
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
                    rationale="",
                    best_book=pick["best_book"],
                    best_odds=pick["best_odds"],
                )
                total_predictions += 1

        logger.info(f"Generated {total_predictions} predictions")
        return get_top_picks(limit=20, min_edge=config.alerts.min_edge)
    finally:
        await fetcher.close()
