"""Snapshot run orchestration for scan execution and persistence lifecycle."""

from __future__ import annotations

import sqlite3
import warnings
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from offsite.core.pathing import get_windows_long_path_warning, to_windows_extended_path
from offsite.core.scan.scanner import ScanResult, scan_source
from offsite.core.state.repository import SnapshotRepository


@dataclass(frozen=True)
class SnapshotRunResult:
    """Outcome summary for a persisted snapshot run."""

    run_id: int
    status: str


def execute_snapshot_run(
    db_path: Path,
    source_root: Path,
    scan_func: Callable[..., ScanResult] = scan_source,
    include_folders: list[Path] | None = None,
    exclude_folders: list[Path] | None = None,
    skip_symlinks: bool = True,
) -> SnapshotRunResult:
    """Execute scan + persistence with running/ok/failed lifecycle transitions."""
    database_path = db_path.resolve()
    warning_text = get_windows_long_path_warning(database_path)
    if warning_text:
        warnings.warn(warning_text, RuntimeWarning, stacklevel=2)

    connect_path = to_windows_extended_path(database_path)
    with closing(sqlite3.connect(connect_path)) as connection:
        repository = SnapshotRepository(connection)
        run_id = repository.create_run_running(source_root.resolve())
        connection.commit()

        try:
            scan_result = scan_func(
                source_root.resolve(),
                skip_symlinks=skip_symlinks,
                include_folders=include_folders,
                exclude_folders=exclude_folders,
            )

            with connection:
                repository.insert_snapshot_files(run_id, scan_result.entries)
                repository.mark_run_ok(run_id)

            return SnapshotRunResult(run_id=run_id, status="ok")
        except Exception as exc:  # pylint: disable=broad-exception-caught
            with connection:
                repository.mark_run_failed(run_id, str(exc))

            return SnapshotRunResult(run_id=run_id, status="failed")
