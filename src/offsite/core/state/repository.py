"""SQLite repository methods for snapshot run and file persistence."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SnapshotRepository:
    """Persistence operations for snapshot_run and snapshot_file records."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Create repository bound to an active SQLite connection."""
        self._connection = connection

    def create_run_running(self, source_root: Path) -> int:
        """Insert a new snapshot run in running state and return its id."""
        started_at = _utc_now_text()
        cursor = self._connection.execute(
            """
            INSERT INTO snapshot_run (started_at, finished_at, status, source_root, notes)
            VALUES (?, NULL, 'running', ?, NULL)
            """,
            (started_at, source_root.as_posix()),
        )
        return int(cursor.lastrowid)

    def mark_run_ok(self, run_id: int) -> None:
        """Mark a snapshot run as successful and set completion time."""
        finished_at = _utc_now_text()
        self._connection.execute(
            """
            UPDATE snapshot_run
            SET status = 'ok', finished_at = ?, notes = NULL
            WHERE id = ?
            """,
            (finished_at, run_id),
        )

    def mark_run_failed(self, run_id: int, error_message: str) -> None:
        """Mark a snapshot run as failed with failure metadata."""
        finished_at = _utc_now_text()
        self._connection.execute(
            """
            UPDATE snapshot_run
            SET status = 'failed', finished_at = ?, notes = ?
            WHERE id = ?
            """,
            (finished_at, error_message, run_id),
        )

    def insert_snapshot_files(self, run_id: int, entries: list[dict[str, Any]]) -> None:
        """Insert snapshot_file rows for the given run id."""
        payload = [
            (
                run_id,
                entry["path_rel"],
                entry["size_bytes"],
                entry["mtime_ns"],
                entry["file_type"],
                entry.get("hash_sha256"),
            )
            for entry in entries
        ]

        self._connection.executemany(
            """
            INSERT INTO snapshot_file (snapshot_id, path_rel, size_bytes, mtime_ns, file_type, hash_sha256)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            payload,
        )


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()
