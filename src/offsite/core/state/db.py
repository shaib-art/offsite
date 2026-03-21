from __future__ import annotations

import sqlite3
import warnings
from contextlib import closing
from pathlib import Path

from offsite.core.pathing import get_windows_long_path_warning, to_windows_extended_path

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


def initialize_database(db_path: Path) -> None:
    """Initialize phase-1 schema in the SQLite database at db_path."""
    database_path = db_path.resolve()
    database_path.parent.mkdir(parents=True, exist_ok=True)

    warning_text = get_windows_long_path_warning(database_path)
    if warning_text:
        warnings.warn(warning_text, RuntimeWarning, stacklevel=2)

    connect_path = to_windows_extended_path(database_path)
    with closing(sqlite3.connect(connect_path)) as conn:
        conn.executescript(SCHEMA_V1)
        conn.commit()
