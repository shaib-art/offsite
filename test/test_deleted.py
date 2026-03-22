"""Tests for deletion retention safety gating."""

from __future__ import annotations

from pathlib import Path

from offsite.core.diff.deleted import is_deletion_candidate
from offsite.core.diff.differ import Differ
from offsite.core.state.db import initialize_database
from offsite.core.state.repository import SnapshotRepository

_DAY_NS = 24 * 60 * 60 * 1_000_000_000


def _seed_snapshot(repository: SnapshotRepository, source_root: Path, entries: list[dict]) -> int:
    """Create and complete a snapshot run populated with provided file rows."""
    run_id = repository.create_run_running(source_root)
    repository.insert_snapshot_files(run_id, entries)
    repository.mark_run_ok(run_id)
    return run_id


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


def test_differ_get_deletable_files_applies_retention_policy(open_sqlite, tmp_path: Path) -> None:
    """Differ should return only deleted entries that satisfy retention age."""
    db_path = tmp_path / "deletion_gate.db"
    initialize_database(db_path)
    evaluation_time_ns = 120 * _DAY_NS

    with open_sqlite(db_path) as connection:
        repository = SnapshotRepository(connection)
        source_root = tmp_path / "ministry_of_silly_walks"

        old_snapshot_id = _seed_snapshot(
            repository,
            source_root,
            [
                {
                    "path_rel": "ministry_of_silly_walks/old_knight.txt",
                    "size_bytes": 1,
                    "mtime_ns": evaluation_time_ns - (35 * _DAY_NS),
                    "file_type": "file",
                },
                {
                    "path_rel": "ministry_of_silly_walks/fresh_shrubbery.txt",
                    "size_bytes": 1,
                    "mtime_ns": evaluation_time_ns - (5 * _DAY_NS),
                    "file_type": "file",
                },
            ],
        )
        new_snapshot_id = _seed_snapshot(repository, source_root, [])
        connection.commit()

        differ = Differ(repository)
        deletable = differ.get_deletable_files(
            old_snapshot_id=old_snapshot_id,
            new_snapshot_id=new_snapshot_id,
            evaluation_time_ns=evaluation_time_ns,
            retention_days=30,
        )

    assert [entry.path for entry in deletable] == [Path("ministry_of_silly_walks/old_knight.txt")]
