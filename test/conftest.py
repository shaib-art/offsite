"""Shared pytest fixtures and test bootstrap configuration."""

import sqlite3
import sys
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Iterator

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture
def open_sqlite():
    """Provide a context manager factory for explicitly closed SQLite connections."""

    @contextmanager
    def _open_sqlite(db_path: Path) -> Iterator[sqlite3.Connection]:
        """Open a SQLite connection for tests and always close it."""
        with closing(sqlite3.connect(db_path)) as conn:
            yield conn

    return _open_sqlite
