import pytest
import sqlite3
from pathlib import Path
from unittest.mock import patch


@pytest.fixture
def temp_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    with patch("config.config.db_path", db_path):
        from db.database import run_migrations
        run_migrations()
        yield db_path
