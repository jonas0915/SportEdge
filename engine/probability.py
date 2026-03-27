import logging
import math
from config import config
from engine.elo import elo_win_probability

logger = logging.getLogger("engine.probability")


def blend_probability(
    elo_prob: float, logistic_prob: float, elo_weight: float = None
) -> float:
    if elo_weight is None:
        elo_weight = config.model.elo_weight
    logistic_weight = 1.0 - elo_weight
    blended = elo_weight * elo_prob + logistic_weight * logistic_prob
    return max(0.01, min(0.99, blended))


def _logistic_from_features(features: dict) -> float:
    """Simple weighted logistic model.
    Uses handcrafted weights until we have enough data for sklearn training.
    Positive weights = favors home team."""
    weights = {
        "home_win_pct": 2.0,
        "away_win_pct": -2.0,
        "home_l10_pct": 1.5,
        "away_l10_pct": -1.5,
        "home_home_pct": 1.0,
        "away_away_pct": -1.0,
        "home_pts_diff": 0.15,
        "away_pts_diff": -0.15,
        "home_streak": 0.5,
        "away_streak": -0.5,
        "home_rest_advantage": 0.3,
    }
    logit = 0.0
    for feature, weight in weights.items():
        logit += features.get(feature, 0) * weight

    prob = 1 / (1 + math.exp(-logit))
    return prob


def model_probability(
    features: dict,
    home_elo: float = 1500,
    away_elo: float = 1500,
    home_advantage: float = 0,
    elo_weight: float = None,
) -> float:
    elo_prob = elo_win_probability(home_elo, away_elo, home_advantage)
    logistic_prob = _logistic_from_features(features)
    blended = blend_probability(elo_prob, logistic_prob, elo_weight)
    logger.debug(
        f"Model: elo={elo_prob:.3f} logistic={logistic_prob:.3f} blended={blended:.3f}"
    )
    return blended
