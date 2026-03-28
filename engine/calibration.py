"""
Brier score confidence calibration.

Brier score = mean((model_prob - outcome)^2)
- 0.0 = perfect
- 0.25 = random / no skill (50/50 at 50% always)
- <0.20 = decent predictive model

calibration_buckets: group predictions into 10 probability bins,
compare predicted midpoint vs actual win rate — shows if model is
over/under confident at each probability range.
"""
import logging
from db.database import get_connection

logger = logging.getLogger("engine.calibration")

# Bin edges: 10 buckets of 10% width
BIN_EDGES = [(i / 10, (i + 1) / 10) for i in range(10)]
BIN_MIDPOINTS = [(lo + hi) / 2 for lo, hi in BIN_EDGES]


def _fetch_resolved_predictions(conn, sport: str | None = None) -> list[dict]:
    """Return all resolved win/loss predictions, optionally filtered by sport."""
    if sport:
        rows = conn.execute(
            """
            SELECT p.model_prob, p.outcome, g.sport
            FROM predictions p
            JOIN games g ON p.game_id = g.id
            WHERE p.outcome IN ('win', 'loss')
              AND g.sport = ?
            """,
            (sport,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT p.model_prob, p.outcome, g.sport
            FROM predictions p
            JOIN games g ON p.game_id = g.id
            WHERE p.outcome IN ('win', 'loss')
            """
        ).fetchall()
    return [dict(r) for r in rows]


def compute_brier_score(sport: str | None = None) -> float | None:
    """
    Compute mean Brier score across all resolved predictions.
    Returns None if no resolved predictions exist.

    outcome=win  -> binary_outcome=1
    outcome=loss -> binary_outcome=0
    """
    conn = get_connection()
    try:
        rows = _fetch_resolved_predictions(conn, sport)
    finally:
        conn.close()

    if not rows:
        return None

    total = sum(
        (row["model_prob"] - (1.0 if row["outcome"] == "win" else 0.0)) ** 2
        for row in rows
    )
    return total / len(rows)


def compute_calibration_buckets(sport: str | None = None) -> list[dict]:
    """
    Group resolved predictions into 10 probability bins (0-10%, 10-20%, ..., 90-100%).

    Returns list of dicts:
        {
            "bin_label": "0-10%",
            "predicted_pct": 5.0,   # midpoint of bin
            "actual_pct": 4.2,      # actual win rate in this bin
            "count": 17,            # number of predictions in bin
        }

    Bins with 0 predictions are still returned with actual_pct=None.
    """
    conn = get_connection()
    try:
        rows = _fetch_resolved_predictions(conn, sport)
    finally:
        conn.close()

    buckets = []
    for (lo, hi), midpoint in zip(BIN_EDGES, BIN_MIDPOINTS):
        label = f"{int(lo*100)}-{int(hi*100)}%"
        bin_rows = [
            r for r in rows
            if lo <= r["model_prob"] < hi
        ]
        # Edge case: include 100% in the last bucket
        if hi == 1.0:
            bin_rows = [
                r for r in rows
                if lo <= r["model_prob"] <= hi
            ]

        count = len(bin_rows)
        if count == 0:
            actual_pct = None
        else:
            wins = sum(1 for r in bin_rows if r["outcome"] == "win")
            actual_pct = round((wins / count) * 100, 1)

        buckets.append({
            "bin_label": label,
            "predicted_pct": round(midpoint * 100, 1),
            "actual_pct": actual_pct,
            "count": count,
        })

    return buckets


def _brier_per_sport(conn) -> dict[str, dict]:
    """Compute Brier score and prediction count per sport."""
    rows = conn.execute(
        """
        SELECT p.model_prob, p.outcome, g.sport
        FROM predictions p
        JOIN games g ON p.game_id = g.id
        WHERE p.outcome IN ('win', 'loss')
        """
    ).fetchall()

    sport_data: dict[str, list] = {}
    for row in rows:
        sport_data.setdefault(row["sport"], []).append(row)

    result = {}
    for sport, sport_rows in sport_data.items():
        total = sum(
            (r["model_prob"] - (1.0 if r["outcome"] == "win" else 0.0)) ** 2
            for r in sport_rows
        )
        result[sport] = {
            "brier_score": round(total / len(sport_rows), 4),
            "count": len(sport_rows),
        }
    return result


def get_calibration_summary() -> dict:
    """
    Returns a full calibration summary dict:
    {
        "overall_brier": 0.1823,          # None if no data
        "total_resolved": 142,
        "per_sport": {
            "nba": {"brier_score": 0.17, "count": 55},
            ...
        },
        "buckets": [ ... ],               # from compute_calibration_buckets()
        "interpretation": "decent",       # "no_data", "random", "poor", "decent", "good"
    }
    """
    conn = get_connection()
    try:
        all_resolved = conn.execute(
            "SELECT COUNT(*) as cnt FROM predictions WHERE outcome IN ('win','loss')"
        ).fetchone()["cnt"]

        overall_brier = None
        per_sport = {}
        if all_resolved > 0:
            # Overall Brier
            rows = conn.execute(
                """
                SELECT p.model_prob, p.outcome
                FROM predictions p
                WHERE p.outcome IN ('win', 'loss')
                """
            ).fetchall()
            total_sq_err = sum(
                (r["model_prob"] - (1.0 if r["outcome"] == "win" else 0.0)) ** 2
                for r in rows
            )
            overall_brier = round(total_sq_err / len(rows), 4)
            per_sport = _brier_per_sport(conn)
    finally:
        conn.close()

    buckets = compute_calibration_buckets()

    # Interpret Brier score
    if overall_brier is None:
        interpretation = "no_data"
    elif overall_brier >= 0.24:
        interpretation = "random"
    elif overall_brier >= 0.20:
        interpretation = "poor"
    elif overall_brier >= 0.15:
        interpretation = "decent"
    else:
        interpretation = "good"

    return {
        "overall_brier": overall_brier,
        "total_resolved": all_resolved,
        "per_sport": per_sport,
        "buckets": buckets,
        "interpretation": interpretation,
    }
