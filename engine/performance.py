"""
Model performance analytics.

Tracks actual win/loss outcomes for resolved predictions:
- Overall win rate, edge quality, best/worst sport
- Daily performance over rolling N-day window
- Edge distribution (do higher-edge picks win more?)
- Per-sport comparison table with Brier scores

Complements calibration.py (probability accuracy) by measuring
raw win/loss results and edge quality.
"""
import logging
from db.database import get_connection

logger = logging.getLogger("engine.performance")


def get_prediction_performance(sport: str | None = None) -> dict:
    """
    Overall prediction performance across all resolved predictions.

    Returns dict:
        total_predictions  — resolved win+loss count
        wins               — count
        losses             — count
        win_rate           — 0-100 float, None if no data
        avg_edge_on_wins   — average edge % on winning picks (0-100)
        avg_edge_on_losses — average edge % on losing picks (0-100)
        best_sport         — sport name with highest win rate (min 10 preds)
        worst_sport        — sport name with lowest win rate (min 10 preds)
    """
    conn = get_connection()
    try:
        if sport:
            rows = conn.execute(
                """
                SELECT p.outcome, p.edge
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
                SELECT p.outcome, p.edge
                FROM predictions p
                JOIN games g ON p.game_id = g.id
                WHERE p.outcome IN ('win', 'loss')
                """
            ).fetchall()

        rows = [dict(r) for r in rows]
        total = len(rows)

        if total == 0:
            return {
                "total_predictions": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": None,
                "avg_edge_on_wins": None,
                "avg_edge_on_losses": None,
                "best_sport": None,
                "worst_sport": None,
            }

        wins = [r for r in rows if r["outcome"] == "win"]
        losses = [r for r in rows if r["outcome"] == "loss"]
        win_count = len(wins)
        loss_count = len(losses)
        win_rate = round((win_count / total) * 100, 1)

        avg_edge_wins = (
            round(sum(r["edge"] * 100 for r in wins) / win_count, 1)
            if win_count > 0 else None
        )
        avg_edge_losses = (
            round(sum(r["edge"] * 100 for r in losses) / loss_count, 1)
            if loss_count > 0 else None
        )

        # Best/worst sport (min 10 resolved predictions)
        sport_rows = conn.execute(
            """
            SELECT g.sport,
                   COUNT(*) as total,
                   SUM(CASE WHEN p.outcome = 'win' THEN 1 ELSE 0 END) as wins
            FROM predictions p
            JOIN games g ON p.game_id = g.id
            WHERE p.outcome IN ('win', 'loss')
            GROUP BY g.sport
            HAVING COUNT(*) >= 10
            """
        ).fetchall()

        best_sport = None
        worst_sport = None
        if sport_rows:
            sport_rates = [
                (dict(r)["sport"], dict(r)["wins"] / dict(r)["total"])
                for r in sport_rows
            ]
            best_sport = max(sport_rates, key=lambda x: x[1])[0]
            worst_sport = min(sport_rates, key=lambda x: x[1])[0]

    finally:
        conn.close()

    return {
        "total_predictions": total,
        "wins": win_count,
        "losses": loss_count,
        "win_rate": win_rate,
        "avg_edge_on_wins": avg_edge_wins,
        "avg_edge_on_losses": avg_edge_losses,
        "best_sport": best_sport,
        "worst_sport": worst_sport,
    }


def get_daily_performance(days: int = 30, sport: str | None = None) -> list[dict]:
    """
    Daily performance summary for the last N days.

    Returns list of dicts (only days with data):
        date              — "YYYY-MM-DD"
        predictions_count — resolved picks that day
        wins              — win count
        losses            — loss count
        win_rate          — 0-100 float
    """
    conn = get_connection()
    try:
        if sport:
            rows = conn.execute(
                """
                SELECT DATE(g.start_time) as date,
                       COUNT(*) as predictions_count,
                       SUM(CASE WHEN p.outcome = 'win' THEN 1 ELSE 0 END) as wins,
                       SUM(CASE WHEN p.outcome = 'loss' THEN 1 ELSE 0 END) as losses
                FROM predictions p
                JOIN games g ON p.game_id = g.id
                WHERE p.outcome IN ('win', 'loss')
                  AND g.sport = ?
                  AND g.start_time >= datetime('now', ? || ' days')
                GROUP BY DATE(g.start_time)
                ORDER BY date DESC
                """,
                (sport, f"-{days}"),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT DATE(g.start_time) as date,
                       COUNT(*) as predictions_count,
                       SUM(CASE WHEN p.outcome = 'win' THEN 1 ELSE 0 END) as wins,
                       SUM(CASE WHEN p.outcome = 'loss' THEN 1 ELSE 0 END) as losses
                FROM predictions p
                JOIN games g ON p.game_id = g.id
                WHERE p.outcome IN ('win', 'loss')
                  AND g.start_time >= datetime('now', ? || ' days')
                GROUP BY DATE(g.start_time)
                ORDER BY date DESC
                """,
                (f"-{days}",),
            ).fetchall()
    finally:
        conn.close()

    result = []
    for r in rows:
        r = dict(r)
        total = r["predictions_count"]
        win_rate = round((r["wins"] / total) * 100, 1) if total > 0 else 0.0
        result.append({
            "date": r["date"],
            "predictions_count": total,
            "wins": r["wins"],
            "losses": r["losses"],
            "win_rate": win_rate,
        })
    return result


def get_edge_distribution(sport: str | None = None) -> list[dict]:
    """
    Win rates broken down by edge bucket.

    Buckets: 0-5%, 5-10%, 10-15%, 15-20%, 20%+

    Returns list of dicts:
        edge_bucket — "0-5%", "5-10%", "10-15%", "15-20%", "20%+"
        count       — total resolved predictions in bucket
        wins        — win count
        losses      — loss count
        win_rate    — 0-100 float, None if count == 0
    """
    BUCKETS = [
        ("0-5%",   0.00, 0.05),
        ("5-10%",  0.05, 0.10),
        ("10-15%", 0.10, 0.15),
        ("15-20%", 0.15, 0.20),
        ("20%+",   0.20, 9.99),
    ]

    conn = get_connection()
    try:
        if sport:
            rows = conn.execute(
                """
                SELECT p.edge, p.outcome
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
                SELECT p.edge, p.outcome
                FROM predictions p
                JOIN games g ON p.game_id = g.id
                WHERE p.outcome IN ('win', 'loss')
                """
            ).fetchall()
        rows = [dict(r) for r in rows]
    finally:
        conn.close()

    result = []
    for label, lo, hi in BUCKETS:
        bucket_rows = [r for r in rows if lo <= r["edge"] < hi]
        count = len(bucket_rows)
        wins = sum(1 for r in bucket_rows if r["outcome"] == "win")
        losses = count - wins
        win_rate = round((wins / count) * 100, 1) if count > 0 else None
        result.append({
            "edge_bucket": label,
            "count": count,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
        })
    return result


def get_sport_comparison() -> list[dict]:
    """
    Per-sport performance summary.

    Returns list of dicts:
        sport       — sport name
        total       — resolved predictions count
        wins        — win count
        losses      — loss count
        win_rate    — 0-100 float
        avg_edge    — average edge on all resolved picks (0-100)
        brier_score — mean Brier score (None if no data)
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT g.sport,
                   COUNT(*) as total,
                   SUM(CASE WHEN p.outcome = 'win' THEN 1 ELSE 0 END) as wins,
                   SUM(CASE WHEN p.outcome = 'loss' THEN 1 ELSE 0 END) as losses,
                   AVG(p.edge) as avg_edge,
                   AVG(
                       (p.model_prob - CASE WHEN p.outcome = 'win' THEN 1.0 ELSE 0.0 END) *
                       (p.model_prob - CASE WHEN p.outcome = 'win' THEN 1.0 ELSE 0.0 END)
                   ) as brier_score
            FROM predictions p
            JOIN games g ON p.game_id = g.id
            WHERE p.outcome IN ('win', 'loss')
            GROUP BY g.sport
            ORDER BY total DESC
            """
        ).fetchall()
    finally:
        conn.close()

    result = []
    for r in rows:
        r = dict(r)
        total = r["total"]
        win_rate = round((r["wins"] / total) * 100, 1) if total > 0 else 0.0
        avg_edge = round(r["avg_edge"] * 100, 1) if r["avg_edge"] is not None else None
        brier = round(r["brier_score"], 4) if r["brier_score"] is not None else None
        result.append({
            "sport": r["sport"],
            "total": total,
            "wins": r["wins"],
            "losses": r["losses"],
            "win_rate": win_rate,
            "avg_edge": avg_edge,
            "brier_score": brier,
        })
    return result
