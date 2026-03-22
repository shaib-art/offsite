"""Bin packing algorithm for assigning files into fixed-capacity drives."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Bin:
    """Remaining allocatable capacity for a single destination drive."""

    drive_index: int
    remaining_bytes: int


@dataclass(frozen=True)
class DriveAllocation:
    """Assignment of files to a single drive slot."""

    drive_index: int
    files: list[Path]
    total_size_bytes: int


class BinPacker:
    """Pack files into fixed-capacity bins using first-fit decreasing."""

    def pack(self, files: list[tuple[Path, int]], bins: list[Bin]) -> list[DriveAllocation]:
        """Return drive allocations where each file is placed in the first bin with room."""
        if not files:
            return []
        working_bins = _build_working_bins(bins)
        sorted_files = sorted(files, key=lambda item: (-item[1], item[0].as_posix()))

        for path, size_bytes in sorted_files:
            placed = False
            for working_bin in working_bins:
                if size_bytes <= working_bin.remaining_bytes:
                    working_bin.files.append(path)
                    working_bin.remaining_bytes -= size_bytes
                    working_bin.total_size_bytes += size_bytes
                    placed = True
                    break

            if not placed:
                raise ValueError(
                    f"File {path.as_posix()!r} requires {size_bytes} bytes and exceeds available free space"
                )

        return [
            DriveAllocation(
                drive_index=working_bin.drive_index,
                files=working_bin.files,
                total_size_bytes=working_bin.total_size_bytes,
            )
            for working_bin in working_bins
            if working_bin.files
        ]


@dataclass
class _WorkingBin:
    """Mutable representation of a bin while files are being allocated."""

    drive_index: int
    remaining_bytes: int
    files: list[Path]
    total_size_bytes: int


def _build_working_bins(bins: list[Bin]) -> list[_WorkingBin]:
    """Validate and normalize bins into deterministic mutable working bins."""
    if not bins:
        raise ValueError("At least one drive bin is required for allocation")
    return [
        _WorkingBin(
            drive_index=bin_info.drive_index,
            remaining_bytes=bin_info.remaining_bytes,
            files=[],
            total_size_bytes=0,
        )
        for bin_info in sorted(bins, key=lambda item: item.drive_index)
        if bin_info.remaining_bytes > 0
    ]
