import logging
import math
from db.database import get_connection

logger = logging.getLogger("engine.elo")


def expected_score(rating_a: float, rating_b: float) -> float:
    return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))


def update_elo(
    rating_a: float, rating_b: float, a_won: bool, k: float = 20
) -> tuple[float, float]:
    ea = expected_score(rating_a, rating_b)
    eb = 1 - ea
    sa = 1.0 if a_won else 0.0
    sb = 1.0 - sa
    new_a = rating_a + k * (sa - ea)
    new_b = rating_b + k * (sb - eb)
    return round(new_a, 1), round(new_b, 1)


def elo_win_probability(
    home_rating: float, away_rating: float, home_advantage: float = 0
) -> float:
    return expected_score(home_rating + home_advantage, away_rating)


def get_elo(sport: str, team_name: str) -> float:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT rating FROM elo_ratings WHERE sport = ? AND team_name = ?",
            (sport, team_name),
        ).fetchone()
        return row["rating"] if row else 1500.0
    finally:
        conn.close()


def save_elo(sport: str, team_name: str, rating: float):
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO elo_ratings (sport, team_name, rating, games_played)
               VALUES (?, ?, ?, 1)
               ON CONFLICT(sport, team_name) DO UPDATE SET
                rating = excluded.rating,
                games_played = games_played + 1,
                updated_at = datetime('now')
            """,
            (sport, team_name, rating),
        )
        conn.commit()
    finally:
        conn.close()
