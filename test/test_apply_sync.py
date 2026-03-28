"""Tests for Phase 3 apply-result contract validation and home ingest."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from offsite.core.apply_sync.contract import (
    build_apply_result_envelope,
    validate_apply_result_envelope,
    write_immutable_apply_result,
)
from offsite.core.apply_sync.ingest import ingest_apply_result
from offsite.core.state.db import initialize_database
from offsite.core.state.repository import SnapshotRepository


def _seed_snapshot(repository: SnapshotRepository, source_root: Path, entries: list[dict]) -> int:
    run_id = repository.create_run_running(source_root)
    repository.insert_snapshot_files(run_id, entries)
    repository.mark_run_ok(run_id)
    return run_id


def _build_valid_envelope(applied_snapshot_id: int) -> dict[str, object]:
    return build_apply_result_envelope(
        apply_run_id="apply-coconut-001",
        source_plan_id="7->8",
        uploaded_run_id="upload-coconut-001",
        applied_snapshot_id=applied_snapshot_id,
        completed_at="2026-03-28T10:00:00+00:00",
        drive_inventory=[
            {
                "drive_label": "Office-01",
                "capacity_bytes": 1000,
                "free_bytes": 500,
            }
        ],
        bytes_written=[{"drive_label": "Office-01", "bytes": 500}],
        bytes_deleted=[{"drive_label": "Office-01", "bytes": 25}],
        file_mappings=[
            {
                "path_rel": "flying_circus/parrot.txt",
                "drive_label": "Office-01",
                "version_token": "v2",
                "content_sha256": "a" * 64,
                "size_bytes": 500,
            }
        ],
        failures=[],
        integrity_summary={"verified_files": 1, "mismatch_count": 0},
    )


def test_validate_apply_result_rejects_missing_required_field() -> None:
    """Apply-result validator should reject envelopes missing required fields."""
    invalid_payload = {
        "schema_version": 1,
        "apply_run_id": "apply-ni-001",
    }

    with pytest.raises(ValueError, match="missing required field"):
        validate_apply_result_envelope(invalid_payload)


def test_validate_apply_result_rejects_bad_envelope_hash() -> None:
    """Apply-result validator should reject tampered envelopes."""
    payload = _build_valid_envelope(applied_snapshot_id=1)
    payload["envelope_sha256"] = "b" * 64

    with pytest.raises(ValueError, match="envelope_sha256"):
        validate_apply_result_envelope(payload)


def test_validate_apply_result_rejects_unknown_schema_version() -> None:
    """Apply-result validator should fail for unsupported schema version."""
    payload = _build_valid_envelope(applied_snapshot_id=1)
    payload["schema_version"] = 2

    with pytest.raises(ValueError, match="schema_version"):
        validate_apply_result_envelope(payload)


def test_validate_apply_result_rejects_invalid_drive_inventory() -> None:
    """Apply-result validator should reject impossible free/capacity values."""
    payload = _build_valid_envelope(applied_snapshot_id=1)
    payload["drive_inventory"] = [
        {
            "drive_label": "Office-01",
            "capacity_bytes": 100,
            "free_bytes": 200,
        }
    ]

    with pytest.raises(ValueError, match="free_bytes"):
        validate_apply_result_envelope(payload)


def test_validate_apply_result_rejects_non_hex_file_mapping_checksum() -> None:
    """Apply-result validator should reject 64-character checksums with non-hex content."""
    payload = _build_valid_envelope(applied_snapshot_id=1)
    payload["file_mappings"] = [
        {
            "path_rel": "flying_circus/parrot.txt",
            "drive_label": "Office-01",
            "version_token": "v2",
            "content_sha256": "z" * 64,
            "size_bytes": 500,
        }
    ]

    with pytest.raises(ValueError, match="64 hex characters"):
        validate_apply_result_envelope(payload)


def test_write_immutable_apply_result_refuses_overwrite(tmp_path: Path) -> None:
    """Apply-result writer should refuse overwriting immutable result envelopes."""
    payload = _build_valid_envelope(applied_snapshot_id=1)
    output_path = tmp_path / "immutable.json"

    write_immutable_apply_result(payload, output_path)

    with pytest.raises(ValueError, match="already exists"):
        write_immutable_apply_result(payload, output_path)


def test_ingest_apply_result_updates_inventory_and_placement(open_sqlite, tmp_path: Path) -> None:
    """Ingest should persist apply history, drive inventory, and placement index rows."""
    db_path = tmp_path / "phase3_ingest.db"
    initialize_database(db_path)

    with open_sqlite(db_path) as connection:
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

    envelope = _build_valid_envelope(applied_snapshot_id=snapshot_id)
    result_path = tmp_path / "office_apply_result.json"
    write_immutable_apply_result(envelope, result_path)

    ingest_result = ingest_apply_result(db_path=db_path, apply_result_path=result_path)

    assert ingest_result.status == "ingested"

    with closing(sqlite3.connect(db_path)) as connection:
        apply_rows = connection.execute("SELECT COUNT(*) FROM office_apply_result").fetchone()[0]
        inventory_rows = connection.execute("SELECT COUNT(*) FROM home_drive_inventory").fetchone()[0]
        placement_rows = connection.execute("SELECT COUNT(*) FROM placement_index").fetchone()[0]

    assert apply_rows == 1
    assert inventory_rows == 1
    assert placement_rows == 1


def test_reingest_same_apply_result_is_idempotent(open_sqlite, tmp_path: Path) -> None:
    """Re-ingesting the same immutable envelope should not duplicate state rows."""
    db_path = tmp_path / "phase3_ingest_idempotent.db"
    initialize_database(db_path)

    with open_sqlite(db_path) as connection:
        repository = SnapshotRepository(connection)
        snapshot_id = _seed_snapshot(
            repository,
            tmp_path / "holy_grail",
            [
                {
                    "path_rel": "holy_grail/bridge.txt",
                    "size_bytes": 123,
                    "mtime_ns": 1,
                    "file_type": "file",
                }
            ],
        )
        connection.commit()

    envelope = _build_valid_envelope(applied_snapshot_id=snapshot_id)
    result_path = tmp_path / "apply_result_idempotent.json"
    write_immutable_apply_result(envelope, result_path)

    first = ingest_apply_result(db_path=db_path, apply_result_path=result_path)
    second = ingest_apply_result(db_path=db_path, apply_result_path=result_path)

    assert first.status == "ingested"
    assert second.status == "already_ingested"

    with closing(sqlite3.connect(db_path)) as connection:
        counts = {
            "apply": connection.execute("SELECT COUNT(*) FROM office_apply_result").fetchone()[0],
            "inventory": connection.execute("SELECT COUNT(*) FROM home_drive_inventory").fetchone()[0],
            "placement": connection.execute("SELECT COUNT(*) FROM placement_index").fetchone()[0],
        }

    assert counts == {"apply": 1, "inventory": 1, "placement": 1}


def test_ingest_apply_result_rejects_non_object_payload(tmp_path: Path) -> None:
    """Ingest should reject JSON payloads that are not object envelopes."""
    db_path = tmp_path / "phase3_ingest_non_object.db"
    initialize_database(db_path)
    payload_path = tmp_path / "bad_payload.json"
    payload_path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="JSON object"):
        ingest_apply_result(db_path=db_path, apply_result_path=payload_path)


def test_ingest_apply_result_rejects_unknown_applied_snapshot(tmp_path: Path) -> None:
    """Ingest should fail when envelope references non-existent applied snapshot."""
    db_path = tmp_path / "phase3_ingest_unknown_snapshot.db"
    initialize_database(db_path)
    envelope = _build_valid_envelope(applied_snapshot_id=999)
    result_path = tmp_path / "unknown_snapshot.json"
    write_immutable_apply_result(envelope, result_path)

    with pytest.raises(ValueError, match="does not exist"):
        ingest_apply_result(db_path=db_path, apply_result_path=result_path)


def test_ingest_apply_result_rejects_same_run_id_with_different_hash(
    open_sqlite,
    tmp_path: Path,
) -> None:
    """Ingest should reject conflicting envelopes that reuse an existing apply_run_id."""
    db_path = tmp_path / "phase3_ingest_conflict.db"
    initialize_database(db_path)

    with open_sqlite(db_path) as connection:
        repository = SnapshotRepository(connection)
        snapshot_id = _seed_snapshot(
            repository,
            tmp_path / "knights",
            [
                {
                    "path_rel": "knights/ni.txt",
                    "size_bytes": 10,
                    "mtime_ns": 1,
                    "file_type": "file",
                }
            ],
        )
        connection.commit()

    first = _build_valid_envelope(applied_snapshot_id=snapshot_id)
    first_path = tmp_path / "first_apply.json"
    write_immutable_apply_result(first, first_path)
    ingest_apply_result(db_path=db_path, apply_result_path=first_path)

    second = build_apply_result_envelope(
        apply_run_id="apply-coconut-001",
        source_plan_id="8->9",
        uploaded_run_id="upload-coconut-001",
        applied_snapshot_id=snapshot_id,
        completed_at="2026-03-28T10:00:00+00:00",
        drive_inventory=[
            {
                "drive_label": "Office-01",
                "capacity_bytes": 1000,
                "free_bytes": 500,
            }
        ],
        bytes_written=[{"drive_label": "Office-01", "bytes": 500}],
        bytes_deleted=[{"drive_label": "Office-01", "bytes": 25}],
        file_mappings=[
            {
                "path_rel": "flying_circus/parrot.txt",
                "drive_label": "Office-01",
                "version_token": "v2",
                "content_sha256": "a" * 64,
                "size_bytes": 500,
            }
        ],
        failures=[],
        integrity_summary={"verified_files": 1, "mismatch_count": 0},
    )
    second_path = tmp_path / "second_apply.json"
    second_path.write_text(json.dumps(second, sort_keys=True), encoding="utf-8")

    with pytest.raises(ValueError, match="envelope hash"):
        ingest_apply_result(db_path=db_path, apply_result_path=second_path)
