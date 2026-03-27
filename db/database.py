import sqlite3
import logging
from pathlib import Path
from config import config

logger = logging.getLogger("db")

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(config.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def run_migrations():
    conn = get_connection()
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS _migrations "
            "(id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "filename TEXT NOT NULL UNIQUE, "
            "applied_at DATETIME NOT NULL DEFAULT (datetime('now')))"
        )
        applied = {
            row["filename"]
            for row in conn.execute("SELECT filename FROM _migrations").fetchall()
        }
        migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        for mf in migration_files:
            if mf.name not in applied:
                logger.info(f"Applying migration: {mf.name}")
                conn.executescript(mf.read_text())
                conn.execute(
                    "INSERT INTO _migrations (filename) VALUES (?)", (mf.name,)
                )
                conn.commit()
                logger.info(f"Applied: {mf.name}")
    finally:
        conn.close()
