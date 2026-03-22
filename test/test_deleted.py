"""Tests for deletion retention safety gating."""

from __future__ import annotations

from pathlib import Path

from offsite.core.diff.deleted import is_deletion_candidate

_DAY_NS = 24 * 60 * 60 * 1_000_000_000


def test_is_deletion_candidate_rejects_29_day_deletion() -> None:
    """Files deleted before retention threshold should not be deletable."""
    evaluation_time_ns = 100 * _DAY_NS
    deleted_at_ns = evaluation_time_ns - (29 * _DAY_NS)

    assert not is_deletion_candidate(
        file_path=Path("bridge_of_death/knight.txt"),
        deleted_at_ns=deleted_at_ns,
        evaluation_time_ns=evaluation_time_ns,
    )


def test_is_deletion_candidate_accepts_30_days() -> None:
    """Files deleted exactly at retention threshold should be deletable."""
    evaluation_time_ns = 100 * _DAY_NS
    deleted_at_ns = evaluation_time_ns - (30 * _DAY_NS)

    assert is_deletion_candidate(
        file_path=Path("camelot/coconut.txt"),
        deleted_at_ns=deleted_at_ns,
        evaluation_time_ns=evaluation_time_ns,
    )


def test_is_deletion_candidate_accepts_31_days() -> None:
    """Files deleted beyond threshold should be deletable."""
    evaluation_time_ns = 100 * _DAY_NS
    deleted_at_ns = evaluation_time_ns - (31 * _DAY_NS)

    assert is_deletion_candidate(
        file_path=Path("spamalot/hamster.txt"),
        deleted_at_ns=deleted_at_ns,
        evaluation_time_ns=evaluation_time_ns,
    )


def test_is_deletion_candidate_rejects_same_day_deletion() -> None:
    """Files deleted today should not be deletable."""
    evaluation_time_ns = 100 * _DAY_NS
    deleted_at_ns = evaluation_time_ns

    assert not is_deletion_candidate(
        file_path=Path("flying_circus/parrot.txt"),
        deleted_at_ns=deleted_at_ns,
        evaluation_time_ns=evaluation_time_ns,
    )
