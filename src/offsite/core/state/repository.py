"""SQLite repository methods for snapshot run and file persistence."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SnapshotFileRecord:
    """A persisted file row associated with a snapshot run."""

    path: Path
    size_bytes: int
    mtime_ns: int
    file_type: str


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
        if cursor.lastrowid is None:
            raise RuntimeError("Failed to persist snapshot_run row")
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

    def get_snapshot_files(self, snapshot_id: int) -> list[SnapshotFileRecord]:
        """Return all persisted files for a snapshot id ordered by relative path."""
        rows = self._connection.execute(
            """
            SELECT path_rel, size_bytes, mtime_ns, file_type
            FROM snapshot_file
            WHERE snapshot_id = ?
            ORDER BY path_rel ASC
            """,
            (snapshot_id,),
        ).fetchall()
        return [
            SnapshotFileRecord(
                path=Path(path_rel),
                size_bytes=size_bytes,
                mtime_ns=mtime_ns,
                file_type=file_type,
            )
            for path_rel, size_bytes, mtime_ns, file_type in rows
        ]

    def snapshot_exists(self, snapshot_id: int) -> bool:
        """Return True when a snapshot_run row exists for the given id."""
        row = self._connection.execute(
            "SELECT 1 FROM snapshot_run WHERE id = ? LIMIT 1",
            (snapshot_id,),
        ).fetchone()
        return row is not None

    def get_snapshot_source_root(self, snapshot_id: int) -> str | None:
        """Return source_root for the snapshot id, or None when missing."""
        row = self._connection.execute(
            "SELECT source_root FROM snapshot_run WHERE id = ?",
            (snapshot_id,),
        ).fetchone()
        if row is None:
            return None
        return str(row[0])

    def get_previous_snapshot_id(self, snapshot_id: int) -> int | None:
        """Return most recent earlier successful snapshot for the same source root."""
        source_root = self.get_snapshot_source_root(snapshot_id)
        if source_root is None:
            return None
        row = self._connection.execute(
            """
            SELECT id
            FROM snapshot_run
            WHERE source_root = ?
              AND status = 'ok'
              AND id < ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (source_root, snapshot_id),
        ).fetchone()
        if row is None:
            return None
        return int(row[0])


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()
