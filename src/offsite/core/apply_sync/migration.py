"""Apply-result envelope schema transition rules and migration handlers."""

from __future__ import annotations

from typing import Any

from offsite.core.apply_sync.contract import build_apply_result_envelope

CURRENT_SCHEMA_VERSION = 1
SUPPORTED_MIGRATION_IDS = {"v0_to_v1"}


def migrate_apply_result_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    """Return payload migrated to current schema version when supported."""
    schema_version = payload.get("schema_version")
    if not isinstance(schema_version, int):
        raise ValueError("apply-result schema_version must be an integer")

    if schema_version == CURRENT_SCHEMA_VERSION:
        return payload

    if schema_version == 0:
        migration_id = payload.get("migration_id")
        if not isinstance(migration_id, str) or migration_id not in SUPPORTED_MIGRATION_IDS:
            raise ValueError("apply-result has unsupported or ambiguous migration identifier")
        return _migrate_v0_to_v1(payload)

    raise ValueError("apply-result has unsupported schema transition")


def _migrate_v0_to_v1(payload: dict[str, Any]) -> dict[str, Any]:
    """Migrate legacy schema-v0 envelope shape into schema-v1 contract."""
    apply_run_id = _require_str(payload, "run_id")
    source_plan_id = _require_str(payload, "plan_id")
    uploaded_run_id = _require_str(payload, "upload_run_id")
    completed_at = _require_str(payload, "completed_at")

    snapshot_id = payload.get("snapshot_id")
    if not isinstance(snapshot_id, int) or snapshot_id <= 0:
        raise ValueError("apply-result legacy snapshot_id must be a positive integer")

    drive_inventory = _require_list(payload, "drive_inventory")
    bytes_written = _require_list(payload, "bytes_written")
    bytes_deleted = _require_list(payload, "bytes_deleted")
    file_mappings = _require_list(payload, "file_mappings")
    failures = _require_list(payload, "failures")

    integrity_summary = payload.get("integrity_summary")
    if not isinstance(integrity_summary, dict):
        raise ValueError("apply-result legacy integrity_summary must be an object")

    return build_apply_result_envelope(
        apply_run_id=apply_run_id,
        source_plan_id=source_plan_id,
        uploaded_run_id=uploaded_run_id,
        applied_snapshot_id=snapshot_id,
        completed_at=completed_at,
        drive_inventory=drive_inventory,
        bytes_written=bytes_written,
        bytes_deleted=bytes_deleted,
        file_mappings=file_mappings,
        failures=failures,
        integrity_summary=integrity_summary,
    )


def _require_str(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"apply-result legacy field {field!r} must be a non-empty string")
    return value


def _require_list(payload: dict[str, Any], field: str) -> list[Any]:
    value = payload.get(field)
    if not isinstance(value, list):
        raise ValueError(f"apply-result legacy field {field!r} must be a list")
    return value
