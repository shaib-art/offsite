"""Tests for recovery diagnostics taxonomy serialization."""

from __future__ import annotations

import pytest

from offsite.core.recovery.diagnostics import build_failure


def test_build_failure_serializes_expected_taxonomy_shape() -> None:
    """Failure diagnostics should serialize deterministic category/code/message/path fields."""
    payload = build_failure(
        category="integrity",
        code="checksum_mismatch",
        message="recovery checksum mismatch for restored payload: holy_grail/map.txt",
        path_rel="holy_grail/map.txt",
    )

    assert payload == {
        "category": "integrity",
        "code": "checksum_mismatch",
        "message": "recovery checksum mismatch for restored payload: holy_grail/map.txt",
        "path_rel": "holy_grail/map.txt",
    }


def test_build_failure_rejects_unknown_category() -> None:
    """Failure diagnostics should reject unsupported operator-facing categories."""
    with pytest.raises(ValueError, match="unsupported failure category"):
        build_failure(
            category="network",
            code="unknown",
            message="unexpected",
        )
