"""Bin packing algorithm for assigning files into fixed-capacity drives."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DriveAllocation:
    """Assignment of files to a single drive slot."""

    drive_index: int
    files: list[Path]
    total_size_bytes: int


class BinPacker:
    """Pack files into fixed-capacity bins using first-fit decreasing."""

    def pack(self, files: list[tuple[Path, int]], capacity_bytes: int) -> list[DriveAllocation]:
        """Return drive allocations where each file is placed in first bin with room."""
        if capacity_bytes <= 0:
            raise ValueError("Drive capacity must be greater than zero bytes")

        sorted_files = sorted(files, key=lambda item: (-item[1], item[0].as_posix()))
        allocations: list[DriveAllocation] = []

        for path, size_bytes in sorted_files:
            if size_bytes > capacity_bytes:
                raise ValueError(f"File '{path.as_posix()}' exceeds drive capacity")

            placed = False
            for index, allocation in enumerate(allocations):
                if allocation.total_size_bytes + size_bytes <= capacity_bytes:
                    updated_files = allocation.files + [path]
                    allocations[index] = DriveAllocation(
                        drive_index=allocation.drive_index,
                        files=updated_files,
                        total_size_bytes=allocation.total_size_bytes + size_bytes,
                    )
                    placed = True
                    break

            if not placed:
                allocations.append(
                    DriveAllocation(
                        drive_index=len(allocations),
                        files=[path],
                        total_size_bytes=size_bytes,
                    )
                )

        return allocations
