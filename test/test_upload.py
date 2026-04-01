"""Tests for Phase 3 upload execution and integrity verification."""

from __future__ import annotations

import json
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from offsite.core.upload.executor import UploadExecutionError, execute_upload
from offsite.core.state.db import initialize_database
from offsite.core.state.repository import SnapshotRepository


class _ConflictOnUpsertCheckpointRepository:
    """Test double that injects conflict at checkpoint upsert time."""

    def get_workflow_checkpoint(self, workflow_kind: str, checkpoint_key: str):
        _ = (workflow_kind, checkpoint_key)
        return None

    def upsert_workflow_checkpoint(
        self,
        workflow_kind: str,
        checkpoint_key: str,
        run_id: str,
        step_index: int,
        payload_json: str,
    ) -> None:
        _ = (workflow_kind, checkpoint_key, run_id, step_index, payload_json)
        raise ValueError("conflict")


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


def test_execute_upload_interrupted_then_resume_from_checkpoint(tmp_path: Path) -> None:
    """Upload should resume deterministically from persisted checkpoint state."""
    source_root = tmp_path / "ministry"
    source_root.mkdir(parents=True)
    (source_root / "alpha.txt").write_text("spam", encoding="utf-8")
    (source_root / "beta.txt").write_text("eggs", encoding="utf-8")

    plan_payload = {
        "new_snapshot_id": "2",
        "old_snapshot_id": "1",
        "diff_summary": {"added": 2, "modified": 0, "deleted": 0, "unchanged": 0},
        "allocation": [
            {
                "drive_label": "Office-01",
                "file_count": 2,
                "size_bytes": 8,
                "files": ["alpha.txt", "beta.txt"],
            }
        ],
        "total_files_to_allocate": 2,
        "total_bytes_allocated": 8,
    }

    db_path = tmp_path / "upload_checkpoint.db"
    initialize_database(db_path)
    checkpoint_key = "1->2:Office-01"
    transport_root = tmp_path / "transport"

    call_count = {"count": 0}

    def flaky_copy(source: Path, destination: Path) -> None:
        call_count["count"] += 1
        if call_count["count"] == 2:
            raise OSError("simulated disconnect")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    with closing(sqlite3.connect(db_path)) as connection:
        repository = SnapshotRepository(connection)
        with pytest.raises(UploadExecutionError, match="failed after retries"):
            execute_upload(
                plan_payload=plan_payload,
                source_root=source_root,
                transport_root=transport_root,
                run_id="upload-coconut-checkpoint",
                retries=0,
                copy_file=flaky_copy,
                checkpoint_repository=repository,
                checkpoint_key=checkpoint_key,
            )
        connection.commit()

    with closing(sqlite3.connect(db_path)) as connection:
        repository = SnapshotRepository(connection)
        checkpoint = repository.get_workflow_checkpoint("upload", checkpoint_key)
        assert checkpoint is not None
        assert checkpoint.step_index == 1

    with closing(sqlite3.connect(db_path)) as connection:
        repository = SnapshotRepository(connection)
        result = execute_upload(
            plan_payload=plan_payload,
            source_root=source_root,
            transport_root=transport_root,
            run_id="upload-coconut-checkpoint",
            retries=0,
            checkpoint_repository=repository,
            checkpoint_key=checkpoint_key,
        )
        connection.commit()

    assert result.verified_files == 2
    assert result.copied_files == 1
    assert result.skipped_files == 1


def test_execute_upload_rejects_conflicting_checkpoint_run_id(tmp_path: Path) -> None:
    """Upload should fail closed when checkpoint run identity conflicts on resume."""
    source_root = tmp_path / "castle"
    source_root.mkdir(parents=True)
    (source_root / "grail.txt").write_text("Ni!", encoding="utf-8")

    plan_payload = _make_plan_payload("grail.txt")
    db_path = tmp_path / "upload_checkpoint_conflict.db"
    initialize_database(db_path)
    checkpoint_key = "1->2:Office-01"

    with closing(sqlite3.connect(db_path)) as connection:
        repository = SnapshotRepository(connection)
        repository.upsert_workflow_checkpoint(
            workflow_kind="upload",
            checkpoint_key=checkpoint_key,
            run_id="upload-old-run",
            step_index=1,
            payload_json='{"completed_files":1}',
        )
        connection.commit()

    with closing(sqlite3.connect(db_path)) as connection:
        repository = SnapshotRepository(connection)
        with pytest.raises(UploadExecutionError, match="conflicting checkpoint run_id"):
            execute_upload(
                plan_payload=plan_payload,
                source_root=source_root,
                transport_root=tmp_path / "transport",
                run_id="upload-new-run",
                checkpoint_repository=repository,
                checkpoint_key=checkpoint_key,
            )


def test_execute_upload_rejects_negative_retries() -> None:
    """Upload should reject negative retry counts."""
    with pytest.raises(ValueError, match="retries"):
        execute_upload(
            plan_payload=_make_plan_payload("episode.txt"),
            source_root=Path("/tmp/source"),
            transport_root=Path("/tmp/transport"),
            retries=-1,
        )


def test_execute_upload_rejects_missing_checkpoint_key(tmp_path: Path) -> None:
    """Upload should require checkpoint_key when checkpoint repository is provided."""
    source_root = tmp_path / "ministry"
    source_root.mkdir(parents=True)
    (source_root / "episode.txt").write_text("spam", encoding="utf-8")

    with closing(sqlite3.connect(tmp_path / "state.db")) as connection:
        repository = SnapshotRepository(connection)
        with pytest.raises(ValueError, match="checkpoint_key"):
            execute_upload(
                plan_payload=_make_plan_payload("episode.txt"),
                source_root=source_root,
                transport_root=tmp_path / "transport",
                checkpoint_repository=repository,
                checkpoint_key=None,
            )


def test_execute_upload_rejects_missing_source_payload(tmp_path: Path) -> None:
    """Upload should fail when plan file is absent from source root."""
    source_root = tmp_path / "missing_source"
    source_root.mkdir(parents=True)

    with pytest.raises(UploadExecutionError, match="source payload missing"):
        execute_upload(
            plan_payload=_make_plan_payload("episode.txt"),
            source_root=source_root,
            transport_root=tmp_path / "transport",
        )


def test_execute_upload_rejects_stale_checkpoint_without_payload(tmp_path: Path) -> None:
    """Upload should fail closed if checkpoint claims progress without destination payload."""
    source_root = tmp_path / "ministry"
    source_root.mkdir(parents=True)
    (source_root / "episode.txt").write_text("spam", encoding="utf-8")

    db_path = tmp_path / "upload_checkpoint_stale.db"
    initialize_database(db_path)
    checkpoint_key = "1->2:Office-01"

    with closing(sqlite3.connect(db_path)) as connection:
        repository = SnapshotRepository(connection)
        repository.upsert_workflow_checkpoint(
            workflow_kind="upload",
            checkpoint_key=checkpoint_key,
            run_id="upload-coconut-stale",
            step_index=1,
            payload_json='{"completed_files":1}',
        )
        connection.commit()

    with closing(sqlite3.connect(db_path)) as connection:
        repository = SnapshotRepository(connection)
        with pytest.raises(UploadExecutionError, match="checkpoint state invalid"):
            execute_upload(
                plan_payload=_make_plan_payload("episode.txt"),
                source_root=source_root,
                transport_root=tmp_path / "transport",
                run_id="upload-coconut-stale",
                checkpoint_repository=repository,
                checkpoint_key=checkpoint_key,
            )


def test_execute_upload_accepts_existing_matching_destination_payload(tmp_path: Path) -> None:
    """Upload should skip copy when destination payload already matches source checksum."""
    source_root = tmp_path / "ministry"
    source_root.mkdir(parents=True)
    source_file = source_root / "episode.txt"
    source_file.write_text("And now for something completely different.", encoding="utf-8")

    result = execute_upload(
        plan_payload=_make_plan_payload("episode.txt"),
        source_root=source_root,
        transport_root=tmp_path / "transport",
        run_id="upload-existing",
    )
    assert result.copied_files == 1

    rerun = execute_upload(
        plan_payload=_make_plan_payload("episode.txt"),
        source_root=source_root,
        transport_root=tmp_path / "transport",
        run_id="upload-existing",
    )
    assert rerun.copied_files == 0
    assert rerun.skipped_files == 1


def test_execute_upload_rejects_conflict_on_checkpoint_upsert(tmp_path: Path) -> None:
    """Upload should fail closed when checkpoint upsert reports conflicting run identity."""
    source_root = tmp_path / "ministry"
    source_root.mkdir(parents=True)
    (source_root / "episode.txt").write_text("spam", encoding="utf-8")

    with pytest.raises(UploadExecutionError, match="conflicting checkpoint run_id"):
        execute_upload(
            plan_payload=_make_plan_payload("episode.txt"),
            source_root=source_root,
            transport_root=tmp_path / "transport",
            run_id="upload-upsert-conflict",
            checkpoint_repository=_ConflictOnUpsertCheckpointRepository(),
            checkpoint_key="1->2:Office-01",
        )
