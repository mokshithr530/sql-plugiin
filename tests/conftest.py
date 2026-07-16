import sqlite3
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


@pytest.fixture(autouse=True)
def clean_backend_state():
    from database_manager import db_manager
    from response_cache import response_cache
    from session_memory import session_memory

    response_cache.client = None

    yield

    db_manager.disconnect()
    response_cache.client = None
    session_memory.reset()


@pytest.fixture
def sample_db(tmp_path):
    db_path = tmp_path / "sample.db"
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        CREATE TABLE people (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            salary INTEGER NOT NULL
        )
        """
    )
    connection.executemany(
        "INSERT INTO people(name, salary) VALUES (?, ?)",
        [
            ("Alice", 100),
            ("Bob", 200),
            ("Cara", 150),
        ],
    )
    connection.commit()
    connection.close()
    return db_path
