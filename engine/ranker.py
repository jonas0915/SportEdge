import logging
from config import config

logger = logging.getLogger("engine.ranker")


def compute_kelly(
    win_prob: float, american_odds: float, fraction: float = None
) -> float:
    if fraction is None:
        fraction = config.kelly.fraction
    if american_odds > 0:
        decimal_odds = american_odds / 100
    else:
        decimal_odds = 100 / abs(american_odds)

    # Kelly formula: f = (bp - q) / b
    b = decimal_odds
    p = win_prob
    q = 1 - p
    kelly = (b * p - q) / b if b > 0 else 0
    kelly = max(kelly, 0) * fraction
    kelly = min(kelly, config.kelly.max_stake_pct)
    return round(kelly, 6)


def compute_score(edge: float, confidence: float, kelly: float) -> float:
    return round(edge * confidence * kelly, 6)


def rank_predictions(
    value_bets: list[dict],
    confidence: float = None,
    kelly_fraction: float = None,
) -> list[dict]:
    if confidence is None:
        confidence = config.model.default_confidence
    if kelly_fraction is None:
        kelly_fraction = config.kelly.fraction

    ranked = []
    for bet in value_bets:
        kelly = compute_kelly(
            bet["model_prob"], bet["best_odds"], fraction=kelly_fraction
        )
        score = compute_score(bet["edge"], confidence, kelly)
        ranked.append({
            **bet,
            "confidence": confidence,
            "kelly_fraction": kelly,
            "score": score,
        })

    ranked.sort(key=lambda x: x["score"], reverse=True)
    for i, r in enumerate(ranked):
        r["rank"] = i + 1

    return ranked
