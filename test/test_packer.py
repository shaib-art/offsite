"""Tests for first-fit decreasing drive packing."""

from __future__ import annotations

from pathlib import Path

import pytest

from offsite.core.plan.packer import BinPacker


def _planned_paths(allocations) -> list[Path]:
    return [path for allocation in allocations for path in allocation.files]


def test_packer_single_small_file_fits_single_drive() -> None:
    """A single file smaller than capacity should produce one allocation."""
    packer = BinPacker()
    files = [(Path("spamalot.dmg"), 10)]

    allocations = packer.pack(files=files, capacity_bytes=100)

    assert len(allocations) == 1
    assert allocations[0].files == [Path("spamalot.dmg")]
    assert allocations[0].total_size_bytes == 10


def test_packer_splits_files_across_two_drives() -> None:
    """Files that cannot fit together should be split into additional drives."""
    packer = BinPacker()
    files = [
        (Path("grail-scripts.tar"), 80),
        (Path("holy_hand_grenade.iso"), 60),
        (Path("knights_who_say_ni.bin"), 40),
    ]

    allocations = packer.pack(files=files, capacity_bytes=100)

    assert len(allocations) == 2
    assert sum(allocation.total_size_bytes for allocation in allocations) == 180


def test_packer_file_exactly_fills_drive() -> None:
    """A file equal to capacity should fill one drive exactly."""
    packer = BinPacker()

    allocations = packer.pack(files=[(Path("black_knight.vhd"), 100)], capacity_bytes=100)

    assert len(allocations) == 1
    assert allocations[0].total_size_bytes == 100


def test_packer_raises_for_file_larger_than_capacity() -> None:
    """Any file exceeding drive capacity should fail fast."""
    packer = BinPacker()

    with pytest.raises(ValueError, match="exceeds"):
        packer.pack(files=[(Path("bridge_of_death.mkv"), 101)], capacity_bytes=100)


def test_packer_empty_file_list_returns_empty_allocations() -> None:
    """No files should produce no drive allocations."""
    packer = BinPacker()

    allocations = packer.pack(files=[], capacity_bytes=100)

    assert allocations == []


def test_packer_keeps_all_files_on_single_drive_when_possible() -> None:
    """If total file size fits one drive, only one allocation is needed."""
    packer = BinPacker()
    files = [
        (Path("ministry/one.txt"), 10),
        (Path("ministry/two.txt"), 20),
        (Path("ministry/three.txt"), 30),
    ]

    allocations = packer.pack(files=files, capacity_bytes=100)

    assert len(allocations) == 1
    assert allocations[0].total_size_bytes == 60


def test_packer_order_independence_for_drive_count() -> None:
    """Input order should not change number of drives used under FFD strategy."""
    packer = BinPacker()
    files_a = [
        (Path("a.txt"), 70),
        (Path("b.txt"), 40),
        (Path("c.txt"), 30),
        (Path("d.txt"), 20),
    ]
    files_b = list(reversed(files_a))

    allocations_a = packer.pack(files=files_a, capacity_bytes=100)
    allocations_b = packer.pack(files=files_b, capacity_bytes=100)

    assert len(allocations_a) == len(allocations_b)
    assert sorted(path.as_posix() for path in _planned_paths(allocations_a)) == sorted(
        path.as_posix() for path in _planned_paths(allocations_b)
    )
