"""Snapshot diff generation between two persisted snapshot ids."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from offsite.core.state.repository import SnapshotFileRecord, SnapshotRepository


@dataclass(frozen=True)
class DiffEntry:
    """Represents a single change between two snapshots."""

    path: Path
    kind: Literal["added", "modified", "deleted", "unchanged"]
    size_bytes: int
    mtime_ns: int
    previous_size: int | None
    previous_mtime_ns: int | None


class Differ:
    """Compare two snapshots and produce diff entries."""

    def __init__(self, repository: SnapshotRepository) -> None:
        """Create a diff engine bound to a snapshot repository."""
        self._repository = repository

    def diff(self, old_snapshot_id: int, new_snapshot_id: int) -> list[DiffEntry]:
        """Load both snapshots from DB, compare rows, and return a path-sorted diff."""
        old_files = _index_by_path(self._repository.get_snapshot_files(old_snapshot_id))
        new_files = _index_by_path(self._repository.get_snapshot_files(new_snapshot_id))

        all_paths = sorted(set(old_files) | set(new_files), key=lambda path: path.as_posix())

        output: list[DiffEntry] = []
        for path in all_paths:
            previous = old_files.get(path)
            current = new_files.get(path)

            if previous is None and current is not None:
                output.append(
                    DiffEntry(
                        path=path,
                        kind="added",
                        size_bytes=current.size_bytes,
                        mtime_ns=current.mtime_ns,
                        previous_size=None,
                        previous_mtime_ns=None,
                    )
                )
                continue

            if previous is not None and current is None:
                output.append(
                    DiffEntry(
                        path=path,
                        kind="deleted",
                        size_bytes=0,
                        mtime_ns=0,
                        previous_size=previous.size_bytes,
                        previous_mtime_ns=previous.mtime_ns,
                    )
                )
                continue

            if previous is None or current is None:
                continue

            if previous.size_bytes != current.size_bytes or previous.mtime_ns != current.mtime_ns:
                kind: Literal["added", "modified", "deleted", "unchanged"] = "modified"
            else:
                kind = "unchanged"

            output.append(
                DiffEntry(
                    path=path,
                    kind=kind,
                    size_bytes=current.size_bytes,
                    mtime_ns=current.mtime_ns,
                    previous_size=previous.size_bytes,
                    previous_mtime_ns=previous.mtime_ns,
                )
            )

        return output


def _index_by_path(files: list[SnapshotFileRecord]) -> dict[Path, SnapshotFileRecord]:
    """Build a lookup keyed by relative path for efficient diff comparison."""
    return {file_record.path: file_record for file_record in files}
