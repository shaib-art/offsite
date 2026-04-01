"""Tests for Phase 4 recovery executor happy-path behavior."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from offsite.core.recovery.contract import build_recovery_request
from offsite.core.recovery.executor import RecoveryExecutionError, execute_recovery
from offsite.core.state.db import initialize_database
from offsite.core.state.repository import SnapshotRepository


def _write_payload(base: Path, drive_label: str, path_rel: str, content: str) -> None:
    target = base / drive_label / path_rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def test_execute_recovery_restores_files_and_writes_report(tmp_path: Path) -> None:
    """Recovery executor should restore payloads and emit immutable report artifact."""
    media_root = tmp_path / "transport" / "upload-coconut-001" / "payloads"
    content = "Ni!\n"
    _write_payload(media_root, "Office-01", "flying_circus/parrot.txt", content)

    request = build_recovery_request(
        restore_run_id="restore-coconut-001",
        source_apply_run_id="apply-coconut-001",
        target_root=(tmp_path / "recovered_home").as_posix(),
        drive_inventory=[
            {"drive_label": "Office-01", "capacity_bytes": 1_000, "free_bytes": 500}
        ],
        files=[
            {
                "path_rel": "flying_circus/parrot.txt",
                "drive_label": "Office-01",
                "content_sha256": _sha256_text(content),
                "size_bytes": len(content.encode("utf-8")),
            }
        ],
    )

    report_path = tmp_path / "reports" / "restore-result.json"
    result = execute_recovery(
        recovery_request=request,
        media_root=media_root,
        report_path=report_path,
    )

    restored_file = tmp_path / "recovered_home" / "flying_circus" / "parrot.txt"
    assert restored_file.read_text(encoding="utf-8") == "Ni!\n"
    assert result.restored_files == 1
    assert result.verified_files == 1

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["restore_run_id"] == "restore-coconut-001"
    assert report["source_apply_run_id"] == "apply-coconut-001"
    assert report["restored_files"] == 1
    assert report["verified_files"] == 1


def test_execute_recovery_sorts_restore_order_deterministically(tmp_path: Path) -> None:
    """Recovery executor should process and report restore entries in sorted order."""
    media_root = tmp_path / "transport" / "upload-coconut-002" / "payloads"
    opening = "eggs"
    finale = "spam"
    _write_payload(media_root, "Office-01", "zulu/finale.txt", finale)
    _write_payload(media_root, "Office-01", "alpha/opening.txt", opening)

    request = build_recovery_request(
        restore_run_id="restore-coconut-002",
        source_apply_run_id="apply-coconut-002",
        target_root=(tmp_path / "recovered_home").as_posix(),
        drive_inventory=[
            {"drive_label": "Office-01", "capacity_bytes": 1_000, "free_bytes": 500}
        ],
        files=[
            {
                "path_rel": "zulu/finale.txt",
                "drive_label": "Office-01",
                "content_sha256": _sha256_text(finale),
                "size_bytes": len(finale.encode("utf-8")),
            },
            {
                "path_rel": "alpha/opening.txt",
                "drive_label": "Office-01",
                "content_sha256": _sha256_text(opening),
                "size_bytes": len(opening.encode("utf-8")),
            },
        ],
    )

    report_path = tmp_path / "reports" / "restore-result.json"
    execute_recovery(recovery_request=request, media_root=media_root, report_path=report_path)

    report = json.loads(report_path.read_text(encoding="utf-8"))
    restored = [entry["path_rel"] for entry in report["restored"]]
    assert restored == ["alpha/opening.txt", "zulu/finale.txt"]


def test_execute_recovery_refuses_overwriting_existing_report(tmp_path: Path) -> None:
    """Recovery report writes should fail when immutable report path already exists."""
    media_root = tmp_path / "transport" / "upload-coconut-003" / "payloads"
    content = "Ni!\n"
    _write_payload(media_root, "Office-01", "flying_circus/parrot.txt", content)

    request = build_recovery_request(
        restore_run_id="restore-coconut-003",
        source_apply_run_id="apply-coconut-003",
        target_root=(tmp_path / "recovered_home").as_posix(),
        drive_inventory=[
            {"drive_label": "Office-01", "capacity_bytes": 1_000, "free_bytes": 500}
        ],
        files=[
            {
                "path_rel": "flying_circus/parrot.txt",
                "drive_label": "Office-01",
                "content_sha256": _sha256_text(content),
                "size_bytes": len(content.encode("utf-8")),
            }
        ],
    )

    report_path = tmp_path / "reports" / "restore-result.json"
    execute_recovery(recovery_request=request, media_root=media_root, report_path=report_path)

    with pytest.raises(RecoveryExecutionError, match="already exists"):
        execute_recovery(recovery_request=request, media_root=media_root, report_path=report_path)


def test_execute_recovery_interrupted_then_resume_from_checkpoint(tmp_path: Path) -> None:
    """Recovery should resume deterministically from persisted checkpoint after interruption."""
    media_root = tmp_path / "transport" / "upload-coconut-004" / "payloads"
    opening = "eggs"
    finale = "spam"
    _write_payload(media_root, "Office-01", "alpha/opening.txt", opening)
    _write_payload(media_root, "Office-01", "zulu/finale.txt", finale)

    request = build_recovery_request(
        restore_run_id="restore-coconut-004",
        source_apply_run_id="apply-coconut-004",
        target_root=(tmp_path / "recovered_home").as_posix(),
        drive_inventory=[
            {"drive_label": "Office-01", "capacity_bytes": 1_000, "free_bytes": 500}
        ],
        files=[
            {
                "path_rel": "zulu/finale.txt",
                "drive_label": "Office-01",
                "content_sha256": _sha256_text(finale),
                "size_bytes": len(finale.encode("utf-8")),
            },
            {
                "path_rel": "alpha/opening.txt",
                "drive_label": "Office-01",
                "content_sha256": _sha256_text(opening),
                "size_bytes": len(opening.encode("utf-8")),
            },
        ],
    )

    db_path = tmp_path / "checkpoint_resume.db"
    initialize_database(db_path)
    checkpoint_key = "apply-coconut-004:/tmp/recovered_home"

    call_count = {"count": 0}

    def flaky_copy(source: Path, destination: Path) -> None:
        call_count["count"] += 1
        if call_count["count"] == 2:
            raise OSError("simulated drive disconnect")
        shutil.copy2(source, destination)

    with closing(sqlite3.connect(db_path)) as connection:
        repository = SnapshotRepository(connection)
        with pytest.raises(RecoveryExecutionError, match="media error"):
            execute_recovery(
                recovery_request=request,
                media_root=media_root,
                report_path=tmp_path / "reports" / "restore-interrupted.json",
                checkpoint_repository=repository,
                checkpoint_key=checkpoint_key,
                copy_file=flaky_copy,
            )
        connection.commit()

    with closing(sqlite3.connect(db_path)) as connection:
        repository = SnapshotRepository(connection)
        checkpoint = repository.get_workflow_checkpoint(
            workflow_kind="recovery",
            checkpoint_key=checkpoint_key,
        )
        assert checkpoint is not None
        assert checkpoint.step_index == 1

    with closing(sqlite3.connect(db_path)) as connection:
        repository = SnapshotRepository(connection)
        resumed = execute_recovery(
            recovery_request=request,
            media_root=media_root,
            report_path=tmp_path / "reports" / "restore-resumed.json",
            checkpoint_repository=repository,
            checkpoint_key=checkpoint_key,
        )
        connection.commit()

    assert resumed.restored_files == 1
    assert resumed.verified_files == 2
    assert (tmp_path / "recovered_home" / "alpha" / "opening.txt").read_text(encoding="utf-8") == opening
    assert (tmp_path / "recovered_home" / "zulu" / "finale.txt").read_text(encoding="utf-8") == finale


def test_execute_recovery_rejects_conflicting_checkpoint_run_id(tmp_path: Path) -> None:
    """Recovery resume should fail closed when checkpoint run identity conflicts."""
    media_root = tmp_path / "transport" / "upload-coconut-005" / "payloads"
    content = "Ni!\n"
    _write_payload(media_root, "Office-01", "flying_circus/parrot.txt", content)

    request = build_recovery_request(
        restore_run_id="restore-coconut-005",
        source_apply_run_id="apply-coconut-005",
        target_root=(tmp_path / "recovered_home").as_posix(),
        drive_inventory=[
            {"drive_label": "Office-01", "capacity_bytes": 1_000, "free_bytes": 500}
        ],
        files=[
            {
                "path_rel": "flying_circus/parrot.txt",
                "drive_label": "Office-01",
                "content_sha256": _sha256_text(content),
                "size_bytes": len(content.encode("utf-8")),
            }
        ],
    )

    db_path = tmp_path / "checkpoint_conflict.db"
    initialize_database(db_path)
    checkpoint_key = "apply-coconut-005:/tmp/recovered_home"

    with closing(sqlite3.connect(db_path)) as connection:
        repository = SnapshotRepository(connection)
        repository.upsert_workflow_checkpoint(
            workflow_kind="recovery",
            checkpoint_key=checkpoint_key,
            run_id="restore-coconut-OLD",
            step_index=1,
            payload_json='{"completed_files":1}',
        )
        connection.commit()

    with closing(sqlite3.connect(db_path)) as connection:
        repository = SnapshotRepository(connection)
        with pytest.raises(RecoveryExecutionError, match="conflicting checkpoint run_id"):
            execute_recovery(
                recovery_request=request,
                media_root=media_root,
                report_path=tmp_path / "reports" / "restore-conflict.json",
                checkpoint_repository=repository,
                checkpoint_key=checkpoint_key,
            )
