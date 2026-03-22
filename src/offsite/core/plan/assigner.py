"""Drive assignment orchestration for diff entries and available HDD slots."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from offsite.core.diff.differ import DiffEntry
from offsite.core.plan.packer import Bin, BinPacker, DriveAllocation


_ABSOLUTE_FREE_FLOOR_BYTES = 10 * 1024 * 1024 * 1024
_PERCENT_FREE_FLOOR = 0.02


@dataclass(frozen=True)
class DriveInfo:
    """Metadata describing an available destination drive."""

    index: int
    label: str
    capacity_bytes: int
    free_bytes: int


@dataclass(frozen=True)
class AssignmentPlan:
    """Plan output describing selected files and per-drive allocations."""

    new_snapshot_id: str
    changes: list[DiffEntry]
    allocations: list[DriveAllocation]
    total_files: int
    total_size_bytes: int
    drives_needed: int


class Assigner:
    """Build an allocation plan from diff entries and drive metadata."""

    def __init__(self, packer: BinPacker | None = None) -> None:
        """Create an assigner with optional custom packer strategy."""
        self._packer = packer or BinPacker()

    def assign(self, diff_entries: list[DiffEntry], available_drives: list[DriveInfo]) -> AssignmentPlan:
        """Assign changed files to drives or raise when capacity is insufficient."""
        _validate_drives(available_drives)

        files_to_allocate = [
            (entry.path, entry.size_bytes)
            for entry in diff_entries
            if entry.kind in {"added", "modified"}
        ]
        if not files_to_allocate:
            return AssignmentPlan(
                new_snapshot_id="",
                changes=diff_entries,
                allocations=[],
                total_files=0,
                total_size_bytes=0,
                drives_needed=0,
            )

        eligible_drives = [
            drive
            for drive in available_drives
            if drive.free_bytes > _reserved_free_bytes_for_drive(drive)
        ]
        if not eligible_drives:
            raise ValueError(
                "No eligible drives with more than required reserved free bytes"
            )

        bins = [
            Bin(
                drive_index=drive.index,
                remaining_bytes=drive.free_bytes - _reserved_free_bytes_for_drive(drive),
            )
            for drive in eligible_drives
        ]
        remapped_allocations = self._packer.pack(files=files_to_allocate, bins=bins)

        return AssignmentPlan(
            new_snapshot_id="",
            changes=diff_entries,
            allocations=remapped_allocations,
            total_files=len(files_to_allocate),
            total_size_bytes=sum(size_bytes for _path, size_bytes in files_to_allocate),
            drives_needed=len(remapped_allocations),
        )


def _validate_drives(available_drives: list[DriveInfo]) -> None:
    """Validate drive list for assignment safety checks before packing."""
    if not available_drives:
        raise ValueError("At least one drive is required for assignment")
    for drive in available_drives:
        if drive.free_bytes < 0:
            raise ValueError("Drive free bytes cannot be negative")
        if drive.free_bytes > drive.capacity_bytes:
            raise ValueError("Drive free bytes cannot exceed total capacity")


def _reserved_free_bytes_for_drive(drive: DriveInfo) -> int:
    """Compute fixed reserve policy: larger of absolute or percentage floor."""
    percentage_floor_bytes = ceil(drive.capacity_bytes * _PERCENT_FREE_FLOOR)
    return max(_ABSOLUTE_FREE_FLOOR_BYTES, percentage_floor_bytes)
