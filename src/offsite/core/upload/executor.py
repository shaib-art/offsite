"""Upload execution pipeline with retry, resume, and checksum verification."""

# pylint: disable=too-many-locals

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from offsite.core.integrity.checksum import sha256_file


class UploadExecutionError(RuntimeError):
    """Raised when upload execution cannot complete safely."""


@dataclass(frozen=True)
class UploadExecutionResult:
    """Stable result contract for upload execution."""

    run_id: str
    source_plan_id: str
    copied_files: int
    skipped_files: int
    verified_files: int
    retry_events: int
    manifest_path: Path


CopyFile = Callable[[Path, Path], None]


def execute_upload(
    plan_payload: dict[str, Any],
    source_root: Path,
    transport_root: Path,
    run_id: str | None = None,
    retries: int = 2,
    copy_file: CopyFile | None = None,
) -> UploadExecutionResult:  # pylint: disable=too-many-locals
    """Upload plan files into transport storage with integrity checks."""
    _validate_plan_payload(plan_payload)
    if retries < 0:
        raise ValueError("retries must be non-negative")

    source_plan_id = f"{plan_payload['old_snapshot_id']}->{plan_payload['new_snapshot_id']}"
    effective_run_id = run_id or _derive_run_id(plan_payload=plan_payload, source_root=source_root)
    run_root = transport_root / effective_run_id
    payload_root = run_root / "payloads"
    payload_root.mkdir(parents=True, exist_ok=True)

    copier = copy_file or _copy_with_shutil
    copied_files = 0
    skipped_files = 0
    verified_files = 0
    retry_events = 0
    manifest_files: list[dict[str, Any]] = []

    for item in _iter_plan_files(plan_payload):
        path_rel = Path(item["path_rel"])
        drive_label = str(item["drive_label"])
        source_path = source_root / path_rel
        if not source_path.exists():
            raise UploadExecutionError(f"source payload missing: {path_rel.as_posix()}")

        destination_path = payload_root / drive_label / path_rel
        destination_path.parent.mkdir(parents=True, exist_ok=True)

        source_hash = sha256_file(source_path)
        if destination_path.exists() and sha256_file(destination_path) == source_hash:
            skipped_files += 1
        else:
            attempts = 0
            while True:
                try:
                    attempts += 1
                    copier(source_path, destination_path)
                    break
                except OSError as exc:
                    if attempts > retries:
                        raise UploadExecutionError(
                            f"upload failed after retries for {path_rel.as_posix()}: {exc}"
                        ) from exc
                    retry_events += 1
            copied_files += 1

        destination_hash = sha256_file(destination_path)
        if destination_hash != source_hash:
            raise UploadExecutionError(
                f"checksum mismatch for uploaded payload: {path_rel.as_posix()}"
            )
        verified_files += 1

        manifest_files.append(
            {
                "drive_label": drive_label,
                "path_rel": path_rel.as_posix(),
                "size_bytes": source_path.stat().st_size,
                "sha256": source_hash,
            }
        )

    manifest_files.sort(key=lambda row: (str(row["drive_label"]), str(row["path_rel"])))
    manifest_payload = {
        "schema_version": 1,
        "run_id": effective_run_id,
        "source_plan_id": source_plan_id,
        "files": manifest_files,
        "integrity": {
            "verified_files": verified_files,
            "mismatch_count": 0,
        },
    }
    manifest_path = run_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest_payload, sort_keys=True), encoding="utf-8")

    return UploadExecutionResult(
        run_id=effective_run_id,
        source_plan_id=source_plan_id,
        copied_files=copied_files,
        skipped_files=skipped_files,
        verified_files=verified_files,
        retry_events=retry_events,
        manifest_path=manifest_path,
    )


def _iter_plan_files(plan_payload: dict[str, Any]) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    for allocation in plan_payload["allocation"]:
        drive_label = str(allocation["drive_label"])
        for file_path in allocation["files"]:
            files.append({"drive_label": drive_label, "path_rel": str(file_path)})
    return sorted(files, key=lambda row: (row["drive_label"], row["path_rel"]))


def _derive_run_id(plan_payload: dict[str, Any], source_root: Path) -> str:
    canonical = {
        "old_snapshot_id": str(plan_payload["old_snapshot_id"]),
        "new_snapshot_id": str(plan_payload["new_snapshot_id"]),
        "allocation": [
            {
                "drive_label": str(allocation["drive_label"]),
                "files": sorted(str(path) for path in allocation["files"]),
            }
            for allocation in sorted(
                plan_payload["allocation"],
                key=lambda row: str(row["drive_label"]),
            )
        ],
        "source_root": source_root.resolve().as_posix(),
    }
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode("utf-8")).hexdigest()
    return f"upload-{digest[:16]}"


def _copy_with_shutil(source: Path, destination: Path) -> None:
    shutil.copy2(source, destination)


def _validate_plan_payload(plan_payload: dict[str, Any]) -> None:
    required = {
        "new_snapshot_id",
        "old_snapshot_id",
        "allocation",
        "total_files_to_allocate",
        "total_bytes_allocated",
    }
    missing = sorted(field for field in required if field not in plan_payload)
    if missing:
        raise ValueError(f"plan payload missing required field(s): {', '.join(missing)}")
    if not isinstance(plan_payload["allocation"], list):
        raise ValueError("plan payload field 'allocation' must be a list")
