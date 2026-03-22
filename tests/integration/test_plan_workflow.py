"""Phase 2 simulation-style integration test for scan->diff->plan workflow."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from offsite.core.diff.differ import Differ
from offsite.core.plan.assigner import Assigner, DriveInfo
from offsite.core.state.db import initialize_database
from offsite.core.state.repository import SnapshotRepository


GIB = 1024 * 1024 * 1024


def _seed_snapshot(repository: SnapshotRepository, source_root: Path, entries: list[dict]) -> int:
    """Create and finalize a snapshot for integration test setup."""
    run_id = repository.create_run_running(source_root)
    repository.insert_snapshot_files(run_id, entries)
    repository.mark_run_ok(run_id)
    return run_id


@pytest.fixture
def mock_nfs_snapshot_1() -> list[dict]:
    """Baseline source snapshot fixture."""
    return [
        {
            "path_rel": "flying_circus/keep.txt",
            "size_bytes": 10,
            "mtime_ns": 1,
            "file_type": "file",
        },
        {
            "path_rel": "flying_circus/remove.txt",
            "size_bytes": 30,
            "mtime_ns": 2,
            "file_type": "file",
        },
        {
            "path_rel": "flying_circus/modify.txt",
            "size_bytes": 50,
            "mtime_ns": 3,
            "file_type": "file",
        },
    ]


@pytest.fixture
def mock_nfs_snapshot_2() -> list[dict]:
    """New source snapshot fixture with adds/modifies/deletes."""
    return [
        {
            "path_rel": "flying_circus/keep.txt",
            "size_bytes": 10,
            "mtime_ns": 1,
            "file_type": "file",
        },
        {
            "path_rel": "flying_circus/modify.txt",
            "size_bytes": 80,
            "mtime_ns": 4,
            "file_type": "file",
        },
        {
            "path_rel": "flying_circus/new.bin",
            "size_bytes": 120,
            "mtime_ns": 5,
            "file_type": "file",
        },
    ]


@pytest.fixture
def mock_drives() -> list[DriveInfo]:
    """Drive fixture with realistic HDD-scale capacities."""
    return [
        DriveInfo(index=0, label="Office-HDD-01", capacity_bytes=500 * GIB, free_bytes=500 * GIB),
        DriveInfo(index=1, label="Office-HDD-02", capacity_bytes=500 * GIB, free_bytes=500 * GIB),
    ]


def test_scan_diff_plan_integration(
    tmp_path: Path,
    mock_nfs_snapshot_1: list[dict],
    mock_nfs_snapshot_2: list[dict],
    mock_drives: list[DriveInfo],
) -> None:
    """End-to-end: scan two snapshots, diff them, plan allocation, verify consistency."""
    db_path = tmp_path / "phase2_simulation.db"
    initialize_database(db_path)

    with sqlite3.connect(db_path) as connection:
        repository = SnapshotRepository(connection)
        source_root = tmp_path / "flying_circus"

        old_snapshot_id = _seed_snapshot(repository, source_root, mock_nfs_snapshot_1)
        new_snapshot_id = _seed_snapshot(repository, source_root, mock_nfs_snapshot_2)
        connection.commit()

        differ = Differ(repository)
        first_diff = differ.diff(old_snapshot_id=old_snapshot_id, new_snapshot_id=new_snapshot_id)
        second_diff = differ.diff(old_snapshot_id=old_snapshot_id, new_snapshot_id=new_snapshot_id)

    # Diff output should be reproducible for deterministic planning.
    assert [entry.path for entry in first_diff] == [entry.path for entry in second_diff]
    assert [entry.kind for entry in first_diff] == [entry.kind for entry in second_diff]

    assigner = Assigner()
    first_plan = assigner.assign(diff_entries=first_diff, available_drives=mock_drives)
    second_plan = assigner.assign(diff_entries=second_diff, available_drives=mock_drives)

    assert first_plan.total_files == 2
    assert first_plan.total_size_bytes == 200

    first_allocated = [path.as_posix() for allocation in first_plan.allocations for path in allocation.files]
    second_allocated = [path.as_posix() for allocation in second_plan.allocations for path in allocation.files]

    # Allocation should include only added/modified files, not deletions.
    assert "flying_circus/new.bin" in first_allocated
    assert "flying_circus/modify.txt" in first_allocated
    assert "flying_circus/remove.txt" not in first_allocated

    # Planning should remain reproducible for the same input snapshots and drives.
    assert first_plan.total_files == second_plan.total_files
    assert first_plan.total_size_bytes == second_plan.total_size_bytes
    assert first_allocated == second_allocated
