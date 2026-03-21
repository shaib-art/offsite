"""Filesystem traversal and metadata collection for scan operations."""

from __future__ import annotations

import os
import warnings
from pathlib import Path
from typing import Any

from offsite.core.scan.filtering import FolderFilter
from offsite.core.pathing import get_windows_long_path_warning, to_windows_extended_path


class ScanResult:
    """Result container for scan entries and non-fatal scan errors."""

    def __init__(
        self,
        entries: list[dict[str, Any]],
        errors: list[dict[str, str]],
        scanned_count: int = 0,
        included_count: int = 0,
        excluded_count: int = 0,
    ) -> None:
        """Create a scan result from collected entries, errors, and summary counters."""
        self.entries = entries
        self.errors = errors
        self.scanned_count = scanned_count
        self.included_count = included_count
        self.excluded_count = excluded_count


def scan_source(
    source_root: Path,
    skip_symlinks: bool = True,
    include_folders: list[Path] | None = None,
    exclude_folders: list[Path] | None = None,
) -> ScanResult:
    """Traverse a source root and return deterministic scan output."""
    root = source_root.resolve()
    warning_text = get_windows_long_path_warning(root)
    if warning_text:
        warnings.warn(warning_text, RuntimeWarning, stacklevel=2)

    folder_filter = FolderFilter(include_folders=include_folders, exclude_folders=exclude_folders)
    entries: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    summary = {
        "scanned_count": 0,
        "included_count": 0,
        "excluded_count": 0,
    }

    _scan_dir(root, root, folder_filter, entries, errors, summary, skip_symlinks)
    entries.sort(key=lambda item: item["path_rel"])

    return ScanResult(
        entries=entries,
        errors=errors,
        scanned_count=summary["scanned_count"],
        included_count=summary["included_count"],
        excluded_count=summary["excluded_count"],
    )


def _scan_dir(
    root: Path,
    current_dir: Path,
    folder_filter: FolderFilter,
    entries: list[dict[str, Any]],
    errors: list[dict[str, str]],
    summary: dict[str, int],
    skip_symlinks: bool,
) -> None:
    """Scan one directory level using root as stable relpath anchor and current_dir as recursion cursor."""
    scan_dir = to_windows_extended_path(current_dir)

    try:
        with os.scandir(scan_dir) as iterator:
            children = sorted(iterator, key=lambda entry: entry.name)
    except OSError as exc:
        errors.append(
            {
                "path_rel": _to_rel_path(root, current_dir),
                "error_type": type(exc).__name__,
            }
        )
        return

    for entry in children:
        abs_path = current_dir / entry.name
        path_rel = _to_rel_path(root, abs_path)

        try:
            if skip_symlinks and entry.is_symlink():
                continue

            summary["scanned_count"] += 1
            stat_result = entry.stat(follow_symlinks=not skip_symlinks)
            if entry.is_dir(follow_symlinks=not skip_symlinks):
                if not folder_filter.should_descend(path_rel):
                    summary["excluded_count"] += 1
                    continue

                if folder_filter.should_include(path_rel):
                    entries.append(
                        {
                            "path_rel": path_rel,
                            "size_bytes": stat_result.st_size,
                            "mtime_ns": stat_result.st_mtime_ns,
                            "file_type": "dir",
                        }
                    )
                    summary["included_count"] += 1
                else:
                    summary["excluded_count"] += 1

                _scan_dir(root, abs_path, folder_filter, entries, errors, summary, skip_symlinks)
                continue

            if entry.is_file(follow_symlinks=not skip_symlinks):
                if not folder_filter.should_include(path_rel):
                    summary["excluded_count"] += 1
                    continue

                entries.append(
                    {
                        "path_rel": path_rel,
                        "size_bytes": stat_result.st_size,
                        "mtime_ns": stat_result.st_mtime_ns,
                        "file_type": "file",
                    }
                )
                summary["included_count"] += 1
        except OSError as exc:
            errors.append(
                {
                    "path_rel": path_rel,
                    "error_type": type(exc).__name__,
                }
            )


def _to_rel_path(root: Path, path: Path) -> str:
    if path == root:
        return "."
    return path.relative_to(root).as_posix()
