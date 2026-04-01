"""Recovery execution pipeline for Phase 4 replay-safe restore."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from offsite.core.integrity.checksum import sha256_file
from offsite.core.recovery.contract import validate_recovery_request
from offsite.core.state.repository import SnapshotRepository


class RecoveryExecutionError(RuntimeError):
    """Raised when recovery execution cannot complete safely."""


@dataclass(frozen=True)
class RecoveryExecutionResult:
    """Stable result contract for recovery execution."""

    restore_run_id: str
    source_apply_run_id: str
    restored_files: int
    verified_files: int
    report_path: Path


CopyFile = Callable[[Path, Path], None]


def execute_recovery(
    recovery_request: dict[str, Any],
    media_root: Path,
    report_path: Path,
    checkpoint_repository: SnapshotRepository | None = None,
    checkpoint_key: str | None = None,
    copy_file: CopyFile | None = None,
) -> RecoveryExecutionResult:
    """Recover payload files from transport media into target root with verification."""
    validate_recovery_request(recovery_request)

    if checkpoint_repository is not None and not checkpoint_key:
        raise ValueError("checkpoint_key is required when checkpoint_repository is provided")

    target_root = Path(str(recovery_request["target_root"]))
    restore_run_id = str(recovery_request["restore_run_id"])
    source_apply_run_id = str(recovery_request["source_apply_run_id"])
    files = sorted(
        recovery_request["files"],
        key=lambda row: str(row["path_rel"]),
    )

    completed_step = _resolve_completed_step(
        checkpoint_repository=checkpoint_repository,
        checkpoint_key=checkpoint_key,
        restore_run_id=restore_run_id,
    )
    copier = copy_file or _copy_with_shutil

    restored_rows: list[dict[str, Any]] = []
    restored_files = 0
    verified_files = 0

    for index, entry in enumerate(files, start=1):
        path_rel = Path(str(entry["path_rel"]))
        drive_label = str(entry["drive_label"])
        expected_sha256 = str(entry["content_sha256"])
        expected_size_bytes = int(entry["size_bytes"])

        source_path = _resolve_under_root(media_root, Path(drive_label) / path_rel)
        if not source_path.exists():
            raise RecoveryExecutionError(f"recovery payload missing: {path_rel.as_posix()}")

        destination_path = _resolve_under_root(target_root, path_rel)
        if index <= completed_step:
            if not destination_path.exists():
                raise RecoveryExecutionError(
                    f"checkpoint state invalid for missing restored payload: {path_rel.as_posix()}"
                )
        else:
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                copier(source_path, destination_path)
            except OSError as exc:
                raise RecoveryExecutionError(
                    f"media error while restoring payload: {path_rel.as_posix()}"
                ) from exc
            restored_files += 1

        if destination_path.stat().st_size != expected_size_bytes:
            raise RecoveryExecutionError(
                f"recovery size mismatch for restored payload: {path_rel.as_posix()}"
            )

        restored_sha256 = sha256_file(destination_path)
        if restored_sha256 != expected_sha256:
            raise RecoveryExecutionError(
                f"recovery checksum mismatch for restored payload: {path_rel.as_posix()}"
            )
        verified_files += 1

        _upsert_checkpoint(
            checkpoint_repository=checkpoint_repository,
            checkpoint_key=checkpoint_key,
            restore_run_id=restore_run_id,
            completed_step=index,
        )

        restored_rows.append(
            {
                "path_rel": path_rel.as_posix(),
                "drive_label": drive_label,
                "size_bytes": expected_size_bytes,
                "content_sha256": restored_sha256,
            }
        )

    report_payload = {
        "schema_version": 1,
        "restore_run_id": restore_run_id,
        "source_apply_run_id": source_apply_run_id,
        "restored_files": restored_files,
        "verified_files": verified_files,
        "restored": restored_rows,
        "failures": [],
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with report_path.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(report_payload, sort_keys=True))
    except FileExistsError as exc:
        raise RecoveryExecutionError("recovery report path already exists; report is immutable") from exc

    return RecoveryExecutionResult(
        restore_run_id=restore_run_id,
        source_apply_run_id=source_apply_run_id,
        restored_files=restored_files,
        verified_files=verified_files,
        report_path=report_path,
    )


def _resolve_completed_step(
    checkpoint_repository: SnapshotRepository | None,
    checkpoint_key: str | None,
    restore_run_id: str,
) -> int:
    if checkpoint_repository is None or checkpoint_key is None:
        return 0

    checkpoint = checkpoint_repository.get_workflow_checkpoint(
        workflow_kind="recovery",
        checkpoint_key=checkpoint_key,
    )
    if checkpoint is None:
        return 0

    if checkpoint.run_id != restore_run_id:
        raise RecoveryExecutionError("conflicting checkpoint run_id for recovery resume")
    return checkpoint.step_index


def _upsert_checkpoint(
    checkpoint_repository: SnapshotRepository | None,
    checkpoint_key: str | None,
    restore_run_id: str,
    completed_step: int,
) -> None:
    if checkpoint_repository is None or checkpoint_key is None:
        return

    payload_json = json.dumps({"completed_files": completed_step}, sort_keys=True)
    try:
        checkpoint_repository.upsert_workflow_checkpoint(
            workflow_kind="recovery",
            checkpoint_key=checkpoint_key,
            run_id=restore_run_id,
            step_index=completed_step,
            payload_json=payload_json,
        )
    except ValueError as exc:
        raise RecoveryExecutionError("conflicting checkpoint run_id for recovery resume") from exc


def _copy_with_shutil(source: Path, destination: Path) -> None:
    shutil.copy2(source, destination)


def _resolve_under_root(root: Path, candidate: Path) -> Path:
    """Resolve a candidate path and ensure it remains inside root."""
    resolved_root = root.resolve()
    resolved_candidate = (resolved_root / candidate).resolve()
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise RecoveryExecutionError(
            f"recovery path escapes allowed root: {candidate.as_posix()}"
        ) from exc
    return resolved_candidate
