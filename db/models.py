import sqlite3
from datetime import datetime, timezone
from db.database import get_connection


def upsert_game(
    sport: str,
    league: str,
    home_team: str,
    away_team: str,
    start_time: datetime,
    api_id: str,
) -> int:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id FROM games WHERE api_id = ?", (api_id,)
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE games SET start_time = ?, status = 'upcoming' WHERE id = ?",
                (start_time.isoformat(), row["id"]),
            )
            conn.commit()
            return row["id"]
        cursor = conn.execute(
            "INSERT INTO games (sport, league, home_team, away_team, start_time, api_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (sport, league, home_team, away_team, start_time.isoformat(), api_id),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def insert_odds(
    game_id: int,
    bookmaker: str,
    bet_type: str,
    selection: str,
    price: float,
    point: float | None = None,
):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO odds (game_id, bookmaker, bet_type, selection, price, point) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (game_id, bookmaker, bet_type, selection, price, point),
        )
        conn.commit()
    finally:
        conn.close()


def insert_prediction(
    game_id: int,
    bet_type: str,
    selection: str,
    model_prob: float,
    market_prob: float,
    edge: float,
    confidence: float,
    kelly_fraction: float,
    score: float,
    rationale: str,
    best_book: str,
    best_odds: float,
):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO predictions "
            "(game_id, bet_type, selection, model_prob, market_prob, edge, "
            "confidence, kelly_fraction, score, rationale, best_book, best_odds) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                game_id, bet_type, selection, model_prob, market_prob, edge,
                confidence, kelly_fraction, score, rationale, best_book, best_odds,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_top_picks(limit: int = 20, min_edge: float = 0.0) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT p.*, g.sport, g.league, g.home_team, g.away_team, g.start_time
            FROM predictions p
            JOIN games g ON p.game_id = g.id
            WHERE g.status = 'upcoming' AND p.edge >= ?
            ORDER BY p.score DESC
            LIMIT ?
            """,
            (min_edge, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_upcoming_games(hours: int = 48) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT g.*, GROUP_CONCAT(DISTINCT o.bookmaker) as bookmakers
            FROM games g
            LEFT JOIN odds o ON g.id = o.game_id
            WHERE g.status = 'upcoming'
              AND g.start_time <= datetime('now', '+' || ? || ' hours')
            GROUP BY g.id
            ORDER BY g.start_time ASC
            """,
            (hours,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_game_odds(game_id: int) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM odds
            WHERE game_id = ?
            ORDER BY timestamp DESC
            """,
            (game_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
