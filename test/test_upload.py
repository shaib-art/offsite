"""Tests for Phase 3 upload execution and integrity verification."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from offsite.core.upload.executor import UploadExecutionError, execute_upload


def _make_plan_payload(path_rel: str) -> dict[str, object]:
    return {
        "new_snapshot_id": "2",
        "old_snapshot_id": "1",
        "diff_summary": {
            "added": 1,
            "modified": 0,
            "deleted": 0,
            "unchanged": 0,
        },
        "allocation": [
            {
                "drive_label": "Office-01",
                "file_count": 1,
                "size_bytes": 20,
                "files": [path_rel],
            }
        ],
        "total_files_to_allocate": 1,
        "total_bytes_allocated": 20,
    }


def test_execute_upload_success_with_retry(tmp_path: Path) -> None:
    """Upload should retry transient copy failures and still produce verified output."""
    source_root = tmp_path / "ministry_of_silly_walks"
    source_root.mkdir(parents=True)
    source_file = source_root / "episode.txt"
    source_file.write_text("And now for something completely different.", encoding="utf-8")

    plan_payload = _make_plan_payload("episode.txt")
    transport_root = tmp_path / "cloud_transport"

    attempts = {"count": 0}

    def flaky_copy(source: Path, destination: Path) -> None:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise OSError("transient transport hiccup")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())

    result = execute_upload(
        plan_payload=plan_payload,
        source_root=source_root,
        transport_root=transport_root,
        retries=2,
        copy_file=flaky_copy,
    )

    assert result.copied_files == 1
    assert result.skipped_files == 0
    assert result.verified_files == 1
    assert result.retry_events == 1

    manifest_payload = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest_payload["run_id"] == result.run_id
    assert manifest_payload["source_plan_id"] == "1->2"


def test_execute_upload_fails_on_checksum_mismatch(tmp_path: Path) -> None:
    """Upload should fail fast when destination checksum differs from source."""
    source_root = tmp_path / "camelot"
    source_root.mkdir(parents=True)
    source_file = source_root / "grail.txt"
    source_file.write_text("Bring out your dead.", encoding="utf-8")

    plan_payload = _make_plan_payload("grail.txt")
    transport_root = tmp_path / "transport"

    def mismatching_copy(_source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("This is not the same payload.", encoding="utf-8")

    with pytest.raises(UploadExecutionError, match="checksum"):
        execute_upload(
            plan_payload=plan_payload,
            source_root=source_root,
            transport_root=transport_root,
            retries=1,
            copy_file=mismatching_copy,
        )


def test_execute_upload_rejects_traversing_payload_path(tmp_path: Path) -> None:
    """Upload should reject relative paths containing parent traversal segments."""
    source_root = tmp_path / "castle"
    source_root.mkdir(parents=True)
    (source_root / "keep.txt").write_text("Ni!", encoding="utf-8")

    plan_payload = _make_plan_payload("../keep.txt")

    with pytest.raises(UploadExecutionError, match="traversal|escapes"):
        execute_upload(
            plan_payload=plan_payload,
            source_root=source_root,
            transport_root=tmp_path / "transport",
        )


def test_execute_upload_rejects_absolute_payload_path(tmp_path: Path) -> None:
    """Upload should reject absolute payload paths from plan input."""
    source_root = tmp_path / "ministry"
    source_root.mkdir(parents=True)
    absolute_file = source_root / "episode.txt"
    absolute_file.write_text("Spam spam spam.", encoding="utf-8")

    plan_payload = _make_plan_payload(str(absolute_file.resolve()))

    with pytest.raises(UploadExecutionError, match="relative"):
        execute_upload(
            plan_payload=plan_payload,
            source_root=source_root,
            transport_root=tmp_path / "transport",
        )


def test_execute_upload_rejects_drive_label_with_separator(tmp_path: Path) -> None:
    """Upload should reject drive labels containing path separator characters."""
    source_root = tmp_path / "bridge"
    source_root.mkdir(parents=True)
    (source_root / "guard.txt").write_text("What is your quest?", encoding="utf-8")

    plan_payload = _make_plan_payload("guard.txt")
    plan_payload["allocation"] = [
        {
            "drive_label": "Office/01",
            "file_count": 1,
            "size_bytes": 20,
            "files": ["guard.txt"],
        }
    ]

    with pytest.raises(UploadExecutionError, match="drive label"):
        execute_upload(
            plan_payload=plan_payload,
            source_root=source_root,
            transport_root=tmp_path / "transport",
        )
