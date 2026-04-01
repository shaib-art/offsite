"""Recovery request contract validation for Phase 4 restore workflows."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

REQUIRED_FIELDS = {
    "schema_version",
    "restore_run_id",
    "source_apply_run_id",
    "target_root",
    "drive_inventory",
    "files",
}


def build_recovery_request(
    restore_run_id: str,
    source_apply_run_id: str,
    target_root: str,
    drive_inventory: list[dict[str, Any]],
    files: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a schema-v1 recovery request payload."""
    return {
        "schema_version": 1,
        "restore_run_id": restore_run_id,
        "source_apply_run_id": source_apply_run_id,
        "target_root": target_root,
        "drive_inventory": drive_inventory,
        "files": files,
    }


def validate_recovery_request(payload: dict[str, Any]) -> None:
    """Validate Phase 4 recovery request structure and safety constraints."""
    missing = sorted(field for field in REQUIRED_FIELDS if field not in payload)
    if missing:
        raise ValueError(f"recovery request missing required field(s): {', '.join(missing)}")

    if payload["schema_version"] != 1:
        raise ValueError("recovery request has unsupported schema_version")

    drive_inventory = payload["drive_inventory"]
    if not isinstance(drive_inventory, list) or not drive_inventory:
        raise ValueError("drive_inventory must be a non-empty list")

    known_drive_labels: set[str] = set()
    for entry in drive_inventory:
        drive_label = _validate_drive_inventory_entry(entry)
        known_drive_labels.add(drive_label)

    files = payload["files"]
    if not isinstance(files, list) or not files:
        raise ValueError("files must be a non-empty list")

    seen_paths: set[str] = set()
    for file_entry in files:
        path_rel, drive_label = _validate_file_entry(file_entry)
        if path_rel in seen_paths:
            raise ValueError(f"files contains duplicate path_rel: {path_rel}")
        seen_paths.add(path_rel)

        if drive_label not in known_drive_labels:
            raise ValueError(f"files references unknown drive_label: {drive_label}")


def _validate_drive_inventory_entry(entry: dict[str, Any]) -> str:
    required = {"drive_label", "capacity_bytes", "free_bytes"}
    missing = sorted(field for field in required if field not in entry)
    if missing:
        raise ValueError(f"drive_inventory entry missing required field(s): {', '.join(missing)}")

    drive_label = str(entry["drive_label"])
    if not drive_label:
        raise ValueError("drive_inventory drive_label must be non-empty")

    capacity_bytes = int(entry["capacity_bytes"])
    free_bytes = int(entry["free_bytes"])

    if capacity_bytes <= 0:
        raise ValueError("drive_inventory capacity_bytes must be positive")
    if free_bytes < 0:
        raise ValueError("drive_inventory free_bytes must be non-negative")
    if free_bytes > capacity_bytes:
        raise ValueError("drive_inventory free_bytes cannot exceed capacity_bytes")

    return drive_label


def _validate_file_entry(entry: dict[str, Any]) -> tuple[str, str]:
    required = {"path_rel", "drive_label", "content_sha256", "size_bytes"}
    missing = sorted(field for field in required if field not in entry)
    if missing:
        raise ValueError(f"files entry missing required field(s): {', '.join(missing)}")

    path_rel = str(entry["path_rel"])
    if not _is_safe_relative_path(path_rel):
        raise ValueError("files path_rel must be a safe relative path")

    drive_label = str(entry["drive_label"])
    if not drive_label:
        raise ValueError("files drive_label must be non-empty")

    checksum = str(entry["content_sha256"])
    if len(checksum) != 64:
        raise ValueError("files content_sha256 must be 64 hex characters")
    try:
        bytes.fromhex(checksum)
    except ValueError:
        raise ValueError("files content_sha256 must be 64 hex characters") from None

    size_bytes = int(entry["size_bytes"])
    if size_bytes < 0:
        raise ValueError("files size_bytes must be non-negative")

    return path_rel, drive_label


def _is_safe_relative_path(path_rel: str) -> bool:
    if not path_rel:
        return False

    path = PurePosixPath(path_rel)
    if path.is_absolute():
        return False

    for part in path.parts:
        if part in {"", ".", ".."}:
            return False

    return True
