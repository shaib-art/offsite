"""Tests for Phase 4 recovery executor happy-path behavior."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from offsite.core.recovery.contract import build_recovery_request
from offsite.core.recovery.executor import RecoveryExecutionError, execute_recovery


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
