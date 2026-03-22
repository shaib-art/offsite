"""Deletion retention policy helpers for safe permanent removals."""

from __future__ import annotations

from pathlib import Path


def is_deletion_candidate(
    file_path: Path,
    deleted_at_ns: int,
    evaluation_time_ns: int,
    retention_days: int = 30,
) -> bool:
    """Return True when a deletion has aged past the configured retention period."""
    del file_path
    elapsed_ns = evaluation_time_ns - deleted_at_ns
    retention_ns = retention_days * 86400 * 10**9
    return elapsed_ns >= retention_ns
