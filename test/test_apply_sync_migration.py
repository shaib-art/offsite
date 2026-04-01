"""Tests for apply-result schema transition and migration handlers."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from offsite.core.apply_sync.ingest import ingest_apply_result
from offsite.core.apply_sync.migration import migrate_apply_result_envelope
from offsite.core.state.db import initialize_database
from offsite.core.state.repository import SnapshotRepository


def _seed_snapshot(repository: SnapshotRepository, source_root: Path, entries: list[dict]) -> int:
    run_id = repository.create_run_running(source_root)
    repository.insert_snapshot_files(run_id, entries)
    repository.mark_run_ok(run_id)
    return run_id


def _legacy_v0_payload(applied_snapshot_id: int) -> dict[str, object]:
    return {
        "schema_version": 0,
        "migration_id": "v0_to_v1",
        "run_id": "apply-coconut-legacy-001",
        "plan_id": "11->12",
        "upload_run_id": "upload-coconut-legacy-001",
        "snapshot_id": applied_snapshot_id,
        "completed_at": "2026-04-01T10:00:00+00:00",
        "drive_inventory": [
            {
                "drive_label": "Office-01",
                "capacity_bytes": 1000,
                "free_bytes": 500,
            }
        ],
        "bytes_written": [{"drive_label": "Office-01", "bytes": 500}],
        "bytes_deleted": [{"drive_label": "Office-01", "bytes": 25}],
        "file_mappings": [
            {
                "path_rel": "flying_circus/parrot.txt",
                "drive_label": "Office-01",
                "version_token": "v2",
                "content_sha256": "a" * 64,
                "size_bytes": 500,
            }
        ],
        "failures": [],
        "integrity_summary": {"verified_files": 1, "mismatch_count": 0},
    }


def test_migrate_apply_result_accepts_supported_v0_transition() -> None:
    """Migration handler should convert supported schema-v0 payloads to schema-v1."""
    migrated = migrate_apply_result_envelope(_legacy_v0_payload(applied_snapshot_id=1))

    assert migrated["schema_version"] == 1
    assert migrated["apply_run_id"] == "apply-coconut-legacy-001"
    assert migrated["source_plan_id"] == "11->12"
    assert migrated["uploaded_run_id"] == "upload-coconut-legacy-001"
    assert migrated["applied_snapshot_id"] == 1
    assert "envelope_sha256" in migrated


def test_migrate_apply_result_rejects_ambiguous_migration_identifier() -> None:
    """Migration should fail when migration identifier is missing or unsupported."""
    payload = _legacy_v0_payload(applied_snapshot_id=1)
    payload["migration_id"] = "v0_to_v2"

    with pytest.raises(ValueError, match="migration identifier"):
        migrate_apply_result_envelope(payload)


def test_migrate_apply_result_rejects_unsupported_schema_transition() -> None:
    """Migration should reject schema versions without registered transitions."""
    payload = {"schema_version": 2}

    with pytest.raises(ValueError, match="unsupported schema transition"):
        migrate_apply_result_envelope(payload)


def test_ingest_apply_result_accepts_supported_v0_migration(tmp_path: Path) -> None:
    """Ingest should accept legacy payloads when a supported migration handler exists."""
    db_path = tmp_path / "phase4_migration_ingest.db"
    initialize_database(db_path)

    with closing(sqlite3.connect(db_path)) as connection:
        repository = SnapshotRepository(connection)
        snapshot_id = _seed_snapshot(
            repository,
            tmp_path / "flying_circus",
            [
                {
                    "path_rel": "flying_circus/parrot.txt",
                    "size_bytes": 500,
                    "mtime_ns": 1,
                    "file_type": "file",
                }
            ],
        )
        connection.commit()

    payload_path = tmp_path / "legacy_apply_result.json"
    payload_path.write_text(
        json.dumps(_legacy_v0_payload(applied_snapshot_id=snapshot_id), sort_keys=True),
        encoding="utf-8",
    )

    result = ingest_apply_result(db_path=db_path, apply_result_path=payload_path)

    assert result.status == "ingested"


def test_ingest_apply_result_rejects_unsupported_schema_transition(tmp_path: Path) -> None:
    """Ingest should reject unsupported schema transitions before state mutation."""
    db_path = tmp_path / "phase4_migration_reject.db"
    initialize_database(db_path)

    payload_path = tmp_path / "unsupported_apply_result.json"
    payload_path.write_text(json.dumps({"schema_version": 2}, sort_keys=True), encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported schema transition"):
        ingest_apply_result(db_path=db_path, apply_result_path=payload_path)
