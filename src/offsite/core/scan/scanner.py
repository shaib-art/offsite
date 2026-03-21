from __future__ import annotations

import os
import warnings
from pathlib import Path
from typing import Any

from offsite.core.pathing import get_windows_long_path_warning, to_windows_extended_path


class ScanResult:
    def __init__(self, entries: list[dict[str, Any]], errors: list[dict[str, str]]) -> None:
        self.entries = entries
        self.errors = errors


def scan_source(source_root: Path, skip_symlinks: bool = True) -> ScanResult:
    root = source_root.resolve()
    warning_text = get_windows_long_path_warning(root)
    if warning_text:
        warnings.warn(warning_text, RuntimeWarning, stacklevel=2)

    entries: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    _scan_dir(root, root, entries, errors, skip_symlinks)
    entries.sort(key=lambda item: item["path_rel"])

    return ScanResult(entries=entries, errors=errors)


def _scan_dir(
    root: Path,
    current_dir: Path,
    entries: list[dict[str, Any]],
    errors: list[dict[str, str]],
    skip_symlinks: bool,
) -> None:
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

            stat_result = entry.stat(follow_symlinks=not skip_symlinks)
            if entry.is_dir(follow_symlinks=not skip_symlinks):
                entries.append(
                    {
                        "path_rel": path_rel,
                        "size_bytes": stat_result.st_size,
                        "mtime_ns": stat_result.st_mtime_ns,
                        "file_type": "dir",
                    }
                )
                _scan_dir(root, abs_path, entries, errors, skip_symlinks)
                continue

            if entry.is_file(follow_symlinks=not skip_symlinks):
                entries.append(
                    {
                        "path_rel": path_rel,
                        "size_bytes": stat_result.st_size,
                        "mtime_ns": stat_result.st_mtime_ns,
                        "file_type": "file",
                    }
                )
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
