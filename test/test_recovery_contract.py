"""Tests for Phase 4 recovery contract validation."""

from __future__ import annotations

import pytest

from offsite.core.recovery.contract import (
    build_recovery_request,
    validate_recovery_request,
)


def _valid_request() -> dict[str, object]:
    return build_recovery_request(
        restore_run_id="restore-001",
        source_apply_run_id="apply-coconut-001",
        target_root="/tmp/recovered_home",
        drive_inventory=[
            {
                "drive_label": "Office-01",
                "capacity_bytes": 1_000,
                "free_bytes": 500,
            }
        ],
        files=[
            {
                "path_rel": "flying_circus/parrot.txt",
                "drive_label": "Office-01",
                "content_sha256": "a" * 64,
                "size_bytes": 500,
            }
        ],
    )


def test_validate_recovery_request_accepts_valid_payload() -> None:
    """Recovery request validator should accept a canonical valid payload."""
    validate_recovery_request(_valid_request())


def test_validate_recovery_request_rejects_missing_required_field() -> None:
    """Recovery request validator should reject envelopes missing required fields."""
    payload = _valid_request()
    del payload["files"]

    with pytest.raises(ValueError, match="missing required field"):
        validate_recovery_request(payload)


def test_validate_recovery_request_rejects_unsupported_schema() -> None:
    """Recovery request validator should reject unknown schema versions."""
    payload = _valid_request()
    payload["schema_version"] = 2

    with pytest.raises(ValueError, match="schema_version"):
        validate_recovery_request(payload)


def test_validate_recovery_request_rejects_duplicate_path_rel() -> None:
    """Recovery request validator should reject duplicate restore mappings."""
    payload = _valid_request()
    payload["files"] = [
        {
            "path_rel": "flying_circus/parrot.txt",
            "drive_label": "Office-01",
            "content_sha256": "a" * 64,
            "size_bytes": 500,
        },
        {
            "path_rel": "flying_circus/parrot.txt",
            "drive_label": "Office-01",
            "content_sha256": "b" * 64,
            "size_bytes": 500,
        },
    ]

    with pytest.raises(ValueError, match="duplicate path_rel"):
        validate_recovery_request(payload)


def test_validate_recovery_request_rejects_unknown_drive_reference() -> None:
    """Recovery request validator should reject file mappings for unknown drives."""
    payload = _valid_request()
    payload["files"] = [
        {
            "path_rel": "flying_circus/parrot.txt",
            "drive_label": "Office-99",
            "content_sha256": "a" * 64,
            "size_bytes": 500,
        }
    ]

    with pytest.raises(ValueError, match="unknown drive_label"):
        validate_recovery_request(payload)


def test_validate_recovery_request_rejects_unsafe_relative_path() -> None:
    """Recovery request validator should reject path traversal outside target root."""
    payload = _valid_request()
    payload["files"] = [
        {
            "path_rel": "../bridge_of_death.txt",
            "drive_label": "Office-01",
            "content_sha256": "a" * 64,
            "size_bytes": 500,
        }
    ]

    with pytest.raises(ValueError, match="safe relative path"):
        validate_recovery_request(payload)


def test_validate_recovery_request_rejects_absolute_relative_path() -> None:
    """Recovery request validator should reject absolute paths in file mappings."""
    payload = _valid_request()
    payload["files"] = [
        {
            "path_rel": "/tmp/holy_grail/map.txt",
            "drive_label": "Office-01",
            "content_sha256": "a" * 64,
            "size_bytes": 500,
        }
    ]

    with pytest.raises(ValueError, match="safe relative path"):
        validate_recovery_request(payload)


def test_validate_recovery_request_rejects_non_list_sections() -> None:
    """Recovery request validator should reject non-list inventory/files sections."""
    payload = _valid_request()
    payload["drive_inventory"] = "Office-01"

    with pytest.raises(ValueError, match="drive_inventory"):
        validate_recovery_request(payload)

    payload = _valid_request()
    payload["files"] = "flying_circus/parrot.txt"

    with pytest.raises(ValueError, match="files"):
        validate_recovery_request(payload)


def test_validate_recovery_request_rejects_invalid_drive_inventory_values() -> None:
    """Recovery request validator should reject impossible drive inventory values."""
    payload = _valid_request()
    payload["drive_inventory"] = [
        {
            "drive_label": "",
            "capacity_bytes": 1_000,
            "free_bytes": 500,
        }
    ]
    with pytest.raises(ValueError, match="drive_label"):
        validate_recovery_request(payload)

    payload = _valid_request()
    payload["drive_inventory"] = [
        {
            "drive_label": "Office-01",
            "capacity_bytes": 0,
            "free_bytes": 0,
        }
    ]
    with pytest.raises(ValueError, match="capacity_bytes"):
        validate_recovery_request(payload)

    payload = _valid_request()
    payload["drive_inventory"] = [
        {
            "drive_label": "Office-01",
            "capacity_bytes": 100,
            "free_bytes": -1,
        }
    ]
    with pytest.raises(ValueError, match="free_bytes"):
        validate_recovery_request(payload)


def test_validate_recovery_request_rejects_invalid_file_entry_values() -> None:
    """Recovery request validator should reject malformed file mapping fields."""
    payload = _valid_request()
    payload["files"] = [
        {
            "path_rel": "flying_circus/parrot.txt",
            "content_sha256": "a" * 64,
            "size_bytes": 500,
        }
    ]
    with pytest.raises(ValueError, match="missing required field"):
        validate_recovery_request(payload)

    payload = _valid_request()
    payload["files"] = [
        {
            "path_rel": "flying_circus/parrot.txt",
            "drive_label": "",
            "content_sha256": "a" * 64,
            "size_bytes": 500,
        }
    ]
    with pytest.raises(ValueError, match="drive_label"):
        validate_recovery_request(payload)

    payload = _valid_request()
    payload["files"] = [
        {
            "path_rel": "flying_circus/parrot.txt",
            "drive_label": "Office-01",
            "content_sha256": "a" * 63,
            "size_bytes": 500,
        }
    ]
    with pytest.raises(ValueError, match="64 hex"):
        validate_recovery_request(payload)

    payload = _valid_request()
    payload["files"] = [
        {
            "path_rel": "flying_circus/parrot.txt",
            "drive_label": "Office-01",
            "content_sha256": "z" * 64,
            "size_bytes": 500,
        }
    ]
    with pytest.raises(ValueError, match="64 hex"):
        validate_recovery_request(payload)

    payload = _valid_request()
    payload["files"] = [
        {
            "path_rel": "flying_circus/parrot.txt",
            "drive_label": "Office-01",
            "content_sha256": "a" * 64,
            "size_bytes": -1,
        }
    ]
    with pytest.raises(ValueError, match="size_bytes"):
        validate_recovery_request(payload)
