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
    assert by_drive[0] == 450
    assert by_drive[1] == 950


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


def test_assigner_ignores_full_drives_when_others_can_fit() -> None:
    """A full drive should be ignored rather than causing assignment failure."""
    assigner = Assigner()
    diff_entries = [
        DiffEntry(
            path=Path("flying_circus/new_clip.bin"),
            kind="added",
            size_bytes=40,
            mtime_ns=1,
            previous_size=None,
            previous_mtime_ns=None,
        ),
    ]
    drives = [
        DriveInfo(index=0, label="Office-HDD-01", capacity_bytes=500, free_bytes=0),
        DriveInfo(index=1, label="Office-HDD-02", capacity_bytes=500, free_bytes=100),
    ]

    plan = assigner.assign(diff_entries=diff_entries, available_drives=drives)

    assert len(plan.allocations) == 1
    assert plan.allocations[0].drive_index == 1
    assert plan.allocations[0].total_size_bytes == 40


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
    """Negative free space should be rejected as invalid drive metadata."""
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
    drives = [DriveInfo(index=0, label="Office-HDD-01", capacity_bytes=100, free_bytes=-1)]

    with pytest.raises(ValueError, match="negative"):
        assigner.assign(diff_entries=diff_entries, available_drives=drives)


def test_assigner_raises_when_no_drive_meets_reserved_free_space_rule() -> None:
    """If all drives are at or below reserved bytes, planning should fail."""
    assigner = Assigner()
    diff_entries = [
        DiffEntry(
            path=Path("camelot/new_file.bin"),
            kind="added",
            size_bytes=10,
            mtime_ns=1,
            previous_size=None,
            previous_mtime_ns=None,
        )
    ]
    drives = [
        DriveInfo(index=0, label="Office-HDD-01", capacity_bytes=500, free_bytes=0),
        DriveInfo(index=1, label="Office-HDD-02", capacity_bytes=500, free_bytes=1),
    ]

    with pytest.raises(ValueError, match="No eligible drives"):
        assigner.assign(diff_entries=diff_entries, available_drives=drives)


def test_assigner_keeps_default_one_byte_reserve_per_drive() -> None:
    """Default planning should avoid consuming a drive's final free byte."""
    assigner = Assigner()
    diff_entries = [
        DiffEntry(
            path=Path("ministry/exact_fit.bin"),
            kind="added",
            size_bytes=100,
            mtime_ns=1,
            previous_size=None,
            previous_mtime_ns=None,
        )
    ]
    drives = [DriveInfo(index=0, label="Office-HDD-01", capacity_bytes=500, free_bytes=100)]

    with pytest.raises(ValueError, match="exact_fit.bin"):
        assigner.assign(diff_entries=diff_entries, available_drives=drives)


def test_assigner_handles_very_large_file_sizes() -> None:
    """Assignment should support very large files (10GB+) without overflow issues."""
    assigner = Assigner()
    eleven_gb = 11 * 1_000_000_000
    diff_entries = [
        DiffEntry(
            path=Path("meaning_of_life/giant_archive.bin"),
            kind="added",
            size_bytes=eleven_gb,
            mtime_ns=1,
            previous_size=None,
            previous_mtime_ns=None,
        )
    ]
    drives = [
        DriveInfo(index=0, label="Office-HDD-01", capacity_bytes=20_000_000_000, free_bytes=20_000_000_000)
    ]

    plan = assigner.assign(diff_entries=diff_entries, available_drives=drives)

    assert plan.total_files == 1
    assert plan.total_size_bytes == eleven_gb


def test_assigner_handles_one_byte_file() -> None:
    """Assignment should support minimal file size payloads."""
    assigner = Assigner()
    diff_entries = [
        DiffEntry(
            path=Path("flying_circus/single_byte.txt"),
            kind="added",
            size_bytes=1,
            mtime_ns=1,
            previous_size=None,
            previous_mtime_ns=None,
        )
    ]
    drives = [DriveInfo(index=0, label="Office-HDD-01", capacity_bytes=10, free_bytes=10)]

    plan = assigner.assign(diff_entries=diff_entries, available_drives=drives)

    assert plan.total_files == 1
    assert plan.total_size_bytes == 1


def test_assigner_fails_when_only_drive_has_zero_capacity() -> None:
    """A zero-free drive should fail planning because no eligible drives remain."""
    assigner = Assigner()
    diff_entries = [
        DiffEntry(
            path=Path("holy_grail/no_space.bin"),
            kind="added",
            size_bytes=1,
            mtime_ns=1,
            previous_size=None,
            previous_mtime_ns=None,
        )
    ]
    drives = [DriveInfo(index=0, label="Office-HDD-01", capacity_bytes=0, free_bytes=0)]

    with pytest.raises(ValueError, match="No eligible drives"):
        assigner.assign(diff_entries=diff_entries, available_drives=drives)
