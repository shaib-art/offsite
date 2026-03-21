from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS snapshot_run (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    source_root TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS snapshot_file (
    snapshot_id INTEGER NOT NULL,
    path_rel TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    file_type TEXT NOT NULL,
    hash_sha256 TEXT,
    FOREIGN KEY (snapshot_id) REFERENCES snapshot_run(id)
);
"""


def initialize_database(db_path: str | Path) -> None:
    """Initialize phase-1 schema in the SQLite database at db_path."""
    database_path = Path(db_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(database_path) as conn:
        conn.executescript(SCHEMA_V1)
        conn.commit()
