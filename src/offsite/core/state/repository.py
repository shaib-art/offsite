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


@dataclass(frozen=True)
class DriveInventoryRecord:
    """A persisted inventory row describing one home-side drive."""

    drive_label: str
    capacity_bytes: int
    free_bytes: int
    apply_result_id: int


@dataclass(frozen=True)
class OfficeApplyResultRecord:  # pylint: disable=too-many-instance-attributes
    """A persisted office apply-result row used for sync and idempotency checks."""

    id: int
    applied_snapshot_id: int
    applied_at: str
    apply_run_id: str | None
    source_plan_id: str | None
    uploaded_run_id: str | None
    completed_at: str | None
    envelope_sha256: str | None


@dataclass(frozen=True)
class WorkflowCheckpointRecord:
    """A persisted workflow checkpoint row for resumable operations."""

    workflow_kind: str
    checkpoint_key: str
    run_id: str
    step_index: int
    payload_json: str
    updated_at: str


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

    def get_snapshot_source_root(self, snapshot_id: int) -> Path | None:
        """Return source_root for the snapshot id, or None when missing."""
        row = self._connection.execute(
            "SELECT source_root FROM snapshot_run WHERE id = ?",
            (snapshot_id,),
        ).fetchone()
        if row is None:
            return None
        return Path(str(row[0]))

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
            (source_root.as_posix(), snapshot_id),
        ).fetchone()
        if row is None:
            return None
        return int(row[0])

    def create_office_apply_result(self, applied_snapshot_id: int) -> int:
        """Create a new office apply-result row and return its id."""
        cursor = self._connection.execute(
            """
            INSERT INTO office_apply_result (
                applied_snapshot_id,
                applied_at,
                apply_run_id,
                source_plan_id,
                uploaded_run_id,
                completed_at,
                envelope_sha256
            )
            VALUES (?, ?, NULL, NULL, NULL, NULL, NULL)
            """,
            (applied_snapshot_id, _utc_now_text()),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("Failed to persist office_apply_result row")
        return int(cursor.lastrowid)

    def create_office_apply_result_envelope(
        self,
        applied_snapshot_id: int,
        apply_run_id: str,
        source_plan_id: str,
        uploaded_run_id: str,
        completed_at: str,
        envelope_sha256: str,
    ) -> int:
        """Persist office apply-result metadata from immutable envelope payload."""
        cursor = self._connection.execute(
            """
            INSERT INTO office_apply_result (
                applied_snapshot_id,
                applied_at,
                apply_run_id,
                source_plan_id,
                uploaded_run_id,
                completed_at,
                envelope_sha256
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                applied_snapshot_id,
                _utc_now_text(),
                apply_run_id,
                source_plan_id,
                uploaded_run_id,
                completed_at,
                envelope_sha256,
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("Failed to persist office_apply_result envelope row")
        return int(cursor.lastrowid)

    def replace_home_drive_inventory(
        self,
        apply_result_id: int,
        drives: list[tuple[str, int, int]],
    ) -> None:
        """Replace persisted inventory rows for a specific apply-result id."""
        self._connection.execute(
            "DELETE FROM home_drive_inventory WHERE apply_result_id = ?",
            (apply_result_id,),
        )
        payload = [
            (label, capacity_bytes, free_bytes, apply_result_id)
            for label, capacity_bytes, free_bytes in drives
        ]
        self._connection.executemany(
            """
            INSERT INTO home_drive_inventory (drive_label, capacity_bytes, free_bytes, apply_result_id)
            VALUES (?, ?, ?, ?)
            """,
            payload,
        )

    def get_latest_office_apply_result_id(self) -> int | None:
        """Return latest office apply-result id, or None when no sync exists."""
        row = self._connection.execute("SELECT id FROM office_apply_result ORDER BY id DESC LIMIT 1").fetchone()
        if row is None:
            return None
        return int(row[0])

    def get_latest_office_apply_result(self) -> OfficeApplyResultRecord | None:
        """Return latest office apply-result row with sync metadata."""
        row = self._connection.execute(
            """
            SELECT
                id,
                applied_snapshot_id,
                applied_at,
                apply_run_id,
                source_plan_id,
                uploaded_run_id,
                completed_at,
                envelope_sha256
            FROM office_apply_result
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            return None
        return OfficeApplyResultRecord(
            id=int(row[0]),
            applied_snapshot_id=int(row[1]),
            applied_at=str(row[2]),
            apply_run_id=None if row[3] is None else str(row[3]),
            source_plan_id=None if row[4] is None else str(row[4]),
            uploaded_run_id=None if row[5] is None else str(row[5]),
            completed_at=None if row[6] is None else str(row[6]),
            envelope_sha256=None if row[7] is None else str(row[7]),
        )

    def get_office_apply_result_by_run_id(self, apply_run_id: str) -> OfficeApplyResultRecord | None:
        """Return office apply-result row for run id, or None when absent."""
        row = self._connection.execute(
            """
            SELECT
                id,
                applied_snapshot_id,
                applied_at,
                apply_run_id,
                source_plan_id,
                uploaded_run_id,
                completed_at,
                envelope_sha256
            FROM office_apply_result
            WHERE apply_run_id = ?
            LIMIT 1
            """,
            (apply_run_id,),
        ).fetchone()
        if row is None:
            return None
        return OfficeApplyResultRecord(
            id=int(row[0]),
            applied_snapshot_id=int(row[1]),
            applied_at=str(row[2]),
            apply_run_id=None if row[3] is None else str(row[3]),
            source_plan_id=None if row[4] is None else str(row[4]),
            uploaded_run_id=None if row[5] is None else str(row[5]),
            completed_at=None if row[6] is None else str(row[6]),
            envelope_sha256=None if row[7] is None else str(row[7]),
        )

    def get_home_drive_inventory(self, apply_result_id: int) -> list[DriveInventoryRecord]:
        """Return persisted drive inventory rows for the specified apply-result id."""
        rows = self._connection.execute(
            """
            SELECT drive_label, capacity_bytes, free_bytes, apply_result_id
            FROM home_drive_inventory
            WHERE apply_result_id = ?
            ORDER BY drive_label ASC
            """,
            (apply_result_id,),
        ).fetchall()
        return [
            DriveInventoryRecord(
                drive_label=str(drive_label),
                capacity_bytes=int(capacity_bytes),
                free_bytes=int(free_bytes),
                apply_result_id=int(row_apply_result_id),
            )
            for drive_label, capacity_bytes, free_bytes, row_apply_result_id in rows
        ]

    def upsert_placement_index(
        self,
        apply_result_id: int,
        mappings: list[tuple[str, str, str, str, int]],
    ) -> None:
        """Upsert placement mappings for files updated by an apply-result run."""
        payload = [
            (
                path_rel,
                drive_label,
                version_token,
                content_sha256,
                size_bytes,
                apply_result_id,
                _utc_now_text(),
            )
            for path_rel, drive_label, version_token, content_sha256, size_bytes in mappings
        ]
        self._connection.executemany(
            """
            INSERT INTO placement_index (
                path_rel,
                drive_label,
                version_token,
                content_sha256,
                size_bytes,
                apply_result_id,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path_rel)
            DO UPDATE SET
                drive_label=excluded.drive_label,
                version_token=excluded.version_token,
                content_sha256=excluded.content_sha256,
                size_bytes=excluded.size_bytes,
                apply_result_id=excluded.apply_result_id,
                updated_at=excluded.updated_at
            """,
            payload,
        )

    def upsert_workflow_checkpoint(
        self,
        workflow_kind: str,
        checkpoint_key: str,
        run_id: str,
        step_index: int,
        payload_json: str,
    ) -> None:
        """Insert or update checkpoint state with atomic run-id conflict protection."""
        cursor = self._connection.execute(
            """
            INSERT INTO workflow_checkpoint (
                workflow_kind,
                checkpoint_key,
                run_id,
                step_index,
                payload_json,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(workflow_kind, checkpoint_key)
            DO UPDATE SET
                run_id=excluded.run_id,
                step_index=excluded.step_index,
                payload_json=excluded.payload_json,
                updated_at=excluded.updated_at
            WHERE workflow_checkpoint.run_id = excluded.run_id
            """,
            (
                workflow_kind,
                checkpoint_key,
                run_id,
                step_index,
                payload_json,
                _utc_now_text(),
            ),
        )
        if cursor.rowcount == 0:
            raise ValueError("conflicting checkpoint run_id for workflow/checkpoint key")

    def get_workflow_checkpoint(
        self,
        workflow_kind: str,
        checkpoint_key: str,
    ) -> WorkflowCheckpointRecord | None:
        """Return checkpoint row for workflow + checkpoint key, if present."""
        row = self._connection.execute(
            """
            SELECT
                workflow_kind,
                checkpoint_key,
                run_id,
                step_index,
                payload_json,
                updated_at
            FROM workflow_checkpoint
            WHERE workflow_kind = ?
              AND checkpoint_key = ?
            LIMIT 1
            """,
            (workflow_kind, checkpoint_key),
        ).fetchone()
        if row is None:
            return None

        return WorkflowCheckpointRecord(
            workflow_kind=str(row[0]),
            checkpoint_key=str(row[1]),
            run_id=str(row[2]),
            step_index=int(row[3]),
            payload_json=str(row[4]),
            updated_at=str(row[5]),
        )


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()
