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
