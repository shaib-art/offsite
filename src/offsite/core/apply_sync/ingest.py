"""Home-side apply-result ingest that updates inventory and placement state."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from offsite.core.pathing import to_windows_extended_path
from offsite.core.apply_sync.contract import validate_apply_result_envelope
from offsite.core.apply_sync.migration import migrate_apply_result_envelope
from offsite.core.state.repository import SnapshotRepository


@dataclass(frozen=True)
class IngestResult:
    """Stable result for apply-result ingest operations."""

    status: str
    apply_result_id: int


def ingest_apply_result(db_path: Path, apply_result_path: Path) -> IngestResult:
    """Ingest immutable apply-result envelope into home state."""
    payload = json.loads(apply_result_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("apply-result payload must be a JSON object")

    payload = migrate_apply_result_envelope(payload)
    validate_apply_result_envelope(payload)

    connect_path = to_windows_extended_path(db_path.resolve())
    with closing(sqlite3.connect(connect_path)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        repository = SnapshotRepository(connection)

        apply_run_id = str(payload["apply_run_id"])
        envelope_sha256 = str(payload["envelope_sha256"])
        existing = repository.get_office_apply_result_by_run_id(apply_run_id)
        if existing is not None:
            if existing.envelope_sha256 != envelope_sha256:
                raise ValueError("apply-result run id already exists with different envelope hash")
            return IngestResult(status="already_ingested", apply_result_id=existing.id)

        applied_snapshot_id = int(payload["applied_snapshot_id"])
        if not repository.snapshot_exists(applied_snapshot_id):
            raise ValueError(f"applied_snapshot_id {applied_snapshot_id} does not exist")

        apply_result_id = repository.create_office_apply_result_envelope(
            applied_snapshot_id=applied_snapshot_id,
            apply_run_id=apply_run_id,
            source_plan_id=str(payload["source_plan_id"]),
            uploaded_run_id=str(payload["uploaded_run_id"]),
            completed_at=str(payload["completed_at"]),
            envelope_sha256=envelope_sha256,
        )

        inventory_rows = [
            (
                str(row["drive_label"]),
                int(row["capacity_bytes"]),
                int(row["free_bytes"]),
            )
            for row in payload["drive_inventory"]
        ]
        repository.replace_home_drive_inventory(apply_result_id=apply_result_id, drives=inventory_rows)

        placement_rows = [
            (
                str(row["path_rel"]),
                str(row["drive_label"]),
                str(row["version_token"]),
                str(row["content_sha256"]),
                int(row["size_bytes"]),
            )
            for row in payload["file_mappings"]
        ]
        repository.upsert_placement_index(apply_result_id=apply_result_id, mappings=placement_rows)

        connection.commit()

    return IngestResult(status="ingested", apply_result_id=apply_result_id)
