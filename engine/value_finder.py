import logging
from collections import defaultdict

logger = logging.getLogger("engine.value")


def american_to_implied_prob(odds: float) -> float:
    if odds == 0:
        return 0.5
    if odds < 0:
        return abs(odds) / (abs(odds) + 100)
    else:
        return 100 / (odds + 100)


def implied_prob_to_american(prob: float) -> float:
    if prob <= 0 or prob >= 1:
        return 0
    if prob == 0.5:
        return 100.0
    if prob > 0.5:
        return -(prob / (1 - prob)) * 100
    else:
        return ((1 - prob) / prob) * 100


def find_consensus_prob(odds_for_selection: list[dict]) -> float:
    if not odds_for_selection:
        return 0.5
    probs = [american_to_implied_prob(o["price"]) for o in odds_for_selection]
    return sum(probs) / len(probs)


def find_value_bets(
    game_odds: list[dict], min_edge: float = 0.05
) -> list[dict]:
    by_selection: dict[str, list[dict]] = defaultdict(list)
    for o in game_odds:
        by_selection[o["selection"]].append(o)

    value_bets = []
    for selection, odds_list in by_selection.items():
        consensus = find_consensus_prob(odds_list)

        for o in odds_list:
            book_implied = american_to_implied_prob(o["price"])
            # Value exists when book implies LOWER probability than consensus
            # (i.e., book is offering better odds than they should)
            edge = consensus - book_implied
            if edge >= min_edge:
                value_bets.append({
                    "selection": selection,
                    "bet_type": o["bet_type"],
                    "model_prob": consensus,
                    "market_prob": book_implied,
                    "edge": edge,
                    "best_book": o["bookmaker"],
                    "best_odds": o["price"],
                    "point": o.get("point"),
                })

    value_bets.sort(key=lambda x: x["edge"], reverse=True)
    return value_bets
