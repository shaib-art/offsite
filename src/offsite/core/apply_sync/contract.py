"""Immutable office apply-result envelope contract."""

# This module intentionally mirrors contract-validation patterns used in other
# workflow contracts to keep each boundary explicit and independently auditable.
# pylint: disable=too-many-arguments,too-many-positional-arguments,duplicate-code

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = {
    "schema_version",
    "apply_run_id",
    "source_plan_id",
    "uploaded_run_id",
    "applied_snapshot_id",
    "completed_at",
    "drive_inventory",
    "bytes_written",
    "bytes_deleted",
    "file_mappings",
    "failures",
    "integrity_summary",
    "envelope_sha256",
}


def build_apply_result_envelope(
    apply_run_id: str,
    source_plan_id: str,
    uploaded_run_id: str,
    applied_snapshot_id: int,
    completed_at: str,
    drive_inventory: list[dict[str, Any]],
    bytes_written: list[dict[str, Any]],
    bytes_deleted: list[dict[str, Any]],
    file_mappings: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    integrity_summary: dict[str, Any],
) -> dict[str, Any]:
    """Build an immutable apply-result envelope with deterministic hash."""
    payload = {
        "schema_version": 1,
        "apply_run_id": apply_run_id,
        "source_plan_id": source_plan_id,
        "uploaded_run_id": uploaded_run_id,
        "applied_snapshot_id": applied_snapshot_id,
        "completed_at": completed_at,
        "drive_inventory": drive_inventory,
        "bytes_written": bytes_written,
        "bytes_deleted": bytes_deleted,
        "file_mappings": file_mappings,
        "failures": failures,
        "integrity_summary": integrity_summary,
    }
    payload["envelope_sha256"] = _compute_envelope_hash(payload)
    return payload


def validate_apply_result_envelope(payload: dict[str, Any]) -> None:
    """Validate envelope structure and deterministic integrity hash."""
    missing = sorted(field for field in REQUIRED_FIELDS if field not in payload)
    if missing:
        raise ValueError(f"apply-result missing required field(s): {', '.join(missing)}")

    if payload["schema_version"] != 1:
        raise ValueError("apply-result has unsupported schema_version")

    if not isinstance(payload["applied_snapshot_id"], int) or payload["applied_snapshot_id"] <= 0:
        raise ValueError("applied_snapshot_id must be a positive integer")

    if not isinstance(payload["drive_inventory"], list) or not payload["drive_inventory"]:
        raise ValueError("drive_inventory must be a non-empty list")

    for entry in payload["drive_inventory"]:
        _validate_drive_inventory_entry(entry)

    if not isinstance(payload["file_mappings"], list):
        raise ValueError("file_mappings must be a list")

    for mapping in payload["file_mappings"]:
        _validate_file_mapping(mapping)

    expected_hash = _compute_envelope_hash(payload)
    if str(payload["envelope_sha256"]) != expected_hash:
        raise ValueError("apply-result envelope_sha256 mismatch")


def write_immutable_apply_result(payload: dict[str, Any], output_path: Path) -> None:
    """Validate and write apply-result once; refusing overwrites preserves immutability."""
    validate_apply_result_envelope(payload)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output_path.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True))
    except FileExistsError:
        raise ValueError("apply-result output path already exists; envelope is immutable") from None


def _compute_envelope_hash(payload: dict[str, Any]) -> str:
    hash_input = {key: value for key, value in payload.items() if key != "envelope_sha256"}
    canonical = json.dumps(hash_input, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_drive_inventory_entry(entry: dict[str, Any]) -> None:
    required = {"drive_label", "capacity_bytes", "free_bytes"}
    missing = sorted(field for field in required if field not in entry)
    if missing:
        raise ValueError(f"drive_inventory entry missing required field(s): {', '.join(missing)}")

    capacity_bytes = int(entry["capacity_bytes"])
    free_bytes = int(entry["free_bytes"])
    if capacity_bytes <= 0:
        raise ValueError("drive_inventory capacity_bytes must be positive")
    if free_bytes < 0:
        raise ValueError("drive_inventory free_bytes must be non-negative")
    if free_bytes > capacity_bytes:
        raise ValueError("drive_inventory free_bytes cannot exceed capacity_bytes")


def _validate_file_mapping(mapping: dict[str, Any]) -> None:
    required = {"path_rel", "drive_label", "version_token", "content_sha256", "size_bytes"}
    missing = sorted(field for field in required if field not in mapping)
    if missing:
        raise ValueError(f"file_mappings entry missing required field(s): {', '.join(missing)}")

    checksum = str(mapping["content_sha256"])
    if len(checksum) != 64:
        raise ValueError("file_mappings content_sha256 must be 64 hex characters")
    try:
        bytes.fromhex(checksum)
    except ValueError:
        raise ValueError("file_mappings content_sha256 must be 64 hex characters") from None
