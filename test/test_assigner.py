"""Tests for diff-to-drive assignment planning."""

from __future__ import annotations

from pathlib import Path

import pytest

from offsite.core.diff.differ import DiffEntry
from offsite.core.plan.assigner import Assigner, DriveInfo


def test_assigner_allocates_added_and_modified_entries() -> None:
    """Assigner should place only added/modified files onto drives."""
    assigner = Assigner()
    diff_entries = [
        DiffEntry(
            path=Path("camelot/new_castle.map"),
            kind="added",
            size_bytes=40,
            mtime_ns=10,
            previous_size=None,
            previous_mtime_ns=None,
        ),
        DiffEntry(
            path=Path("camelot/updated_schedule.txt"),
            kind="modified",
            size_bytes=30,
            mtime_ns=11,
            previous_size=10,
            previous_mtime_ns=5,
        ),
        DiffEntry(
            path=Path("camelot/old_banner.txt"),
            kind="deleted",
            size_bytes=0,
            mtime_ns=0,
            previous_size=12,
            previous_mtime_ns=2,
        ),
        DiffEntry(
            path=Path("camelot/already_synced.txt"),
            kind="unchanged",
            size_bytes=99,
            mtime_ns=12,
            previous_size=99,
            previous_mtime_ns=12,
        ),
    ]
    drives = [
        DriveInfo(index=0, label="Office-HDD-01", capacity_bytes=100, free_bytes=100),
        DriveInfo(index=1, label="Office-HDD-02", capacity_bytes=100, free_bytes=100),
    ]

    plan = assigner.assign(diff_entries=diff_entries, available_drives=drives)

    assert plan.total_files == 2
    assert plan.total_size_bytes == 70
    assert plan.drives_needed == 1
    assert len(plan.allocations) == 1
    allocated_paths = [path for allocation in plan.allocations for path in allocation.files]
    assert Path("camelot/new_castle.map") in allocated_paths
    assert Path("camelot/updated_schedule.txt") in allocated_paths
    assert Path("camelot/old_banner.txt") not in allocated_paths
    assert Path("camelot/already_synced.txt") not in allocated_paths


def test_assigner_supports_mixed_drive_sizes_and_free_space() -> None:
    """Assigner should use per-drive free bytes rather than a uniform capacity."""
    assigner = Assigner()
    diff_entries = [
        DiffEntry(
            path=Path("bridge_of_death/one.bin"),
            kind="added",
            size_bytes=700,
            mtime_ns=1,
            previous_size=None,
            previous_mtime_ns=None,
        ),
        DiffEntry(
            path=Path("bridge_of_death/two.bin"),
            kind="added",
            size_bytes=450,
            mtime_ns=2,
            previous_size=None,
            previous_mtime_ns=None,
        ),
        DiffEntry(
            path=Path("bridge_of_death/three.bin"),
            kind="added",
            size_bytes=250,
            mtime_ns=3,
            previous_size=None,
            previous_mtime_ns=None,
        ),
    ]
    drives = [
        DriveInfo(index=0, label="Office-HDD-01", capacity_bytes=2_000, free_bytes=500),
        DriveInfo(index=1, label="Office-HDD-02", capacity_bytes=2_000, free_bytes=1_000),
    ]

    plan = assigner.assign(diff_entries=diff_entries, available_drives=drives)

    assert plan.total_files == 3
    assert plan.total_size_bytes == 1_400
    assert len(plan.allocations) == 2
    by_drive = {allocation.drive_index: allocation.total_size_bytes for allocation in plan.allocations}
    assert by_drive[0] == 500
    assert by_drive[1] == 900


def test_assigner_uses_only_remaining_space_on_partially_used_drives() -> None:
    """Planning must treat only free bytes as allocatable on existing drives."""
    assigner = Assigner()
    diff_entries = [
        DiffEntry(
            path=Path("ni/partial.bin"),
            kind="added",
            size_bytes=90,
            mtime_ns=1,
            previous_size=None,
            previous_mtime_ns=None,
        ),
        DiffEntry(
            path=Path("ni/partial_2.bin"),
            kind="added",
            size_bytes=60,
            mtime_ns=2,
            previous_size=None,
            previous_mtime_ns=None,
        ),
    ]
    drives = [
        DriveInfo(index=0, label="Office-HDD-01", capacity_bytes=500, free_bytes=100),
        DriveInfo(index=1, label="Office-HDD-02", capacity_bytes=500, free_bytes=100),
    ]

    plan = assigner.assign(diff_entries=diff_entries, available_drives=drives)

    assert plan.total_size_bytes == 150
    assert len(plan.allocations) == 2


def test_assigner_raises_when_files_do_not_fit_available_drives() -> None:
    """Assigner should fail with exact reason when no drive can fit a file."""
    assigner = Assigner()
    diff_entries = [
        DiffEntry(
            path=Path("bridge_of_death/too_large.bin"),
            kind="added",
            size_bytes=180,
            mtime_ns=1,
            previous_size=None,
            previous_mtime_ns=None,
        ),
    ]
    drives = [DriveInfo(index=0, label="Office-HDD-01", capacity_bytes=100, free_bytes=100)]

    with pytest.raises(ValueError, match="too_large.bin") as error:
        assigner.assign(diff_entries=diff_entries, available_drives=drives)

    assert "180" in str(error.value)


def test_assigner_raises_for_invalid_drive_free_space() -> None:
    """Drive free space cannot be zero or negative for assignment planning."""
    assigner = Assigner()
    diff_entries = [
        DiffEntry(
            path=Path("ni/archive.tar"),
            kind="added",
            size_bytes=1,
            mtime_ns=1,
            previous_size=None,
            previous_mtime_ns=None,
        )
    ]
    drives = [DriveInfo(index=0, label="Office-HDD-01", capacity_bytes=100, free_bytes=0)]

    with pytest.raises(ValueError, match="free bytes"):
        assigner.assign(diff_entries=diff_entries, available_drives=drives)
