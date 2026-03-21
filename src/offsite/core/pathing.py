from __future__ import annotations

import sys
from pathlib import Path

WINDOWS_LONG_PATH_WARNING_THRESHOLD = 240
WINDOWS_LONG_PATHS_REG_PATH = r"SYSTEM\CurrentControlSet\Control\FileSystem"
WINDOWS_LONG_PATHS_REG_VALUE = "LongPathsEnabled"


def to_windows_extended_path(path: Path) -> Path:
    """Return a Windows extended-length path when running on Windows."""
    if sys.platform != "win32":
        return path

    path_text = str(path)
    if path_text.startswith("\\\\?\\"):
        return path

    if path_text.startswith("\\\\"):
        unc_tail = path_text.lstrip("\\")
        return Path(f"\\\\?\\UNC\\{unc_tail}")

    return Path(f"\\\\?\\{path_text}")


def get_windows_long_path_warning(path: Path) -> str | None:
    """Return warning text if Windows long path policy may block operations."""
    if sys.platform != "win32":
        return None

    if len(str(path)) < WINDOWS_LONG_PATH_WARNING_THRESHOLD:
        return None

    long_paths_enabled = _read_windows_long_paths_enabled()
    if long_paths_enabled is True:
        return None

    return (
        "Path length may exceed default Windows limits. "
        "Enable HKLM\\SYSTEM\\CurrentControlSet\\Control\\FileSystem\\LongPathsEnabled=1 "
        "or use an execution environment that supports long paths."
    )


def _read_windows_long_paths_enabled() -> bool | None:
    try:
        import winreg
    except ModuleNotFoundError:
        return None

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, WINDOWS_LONG_PATHS_REG_PATH) as registry_key:
            value, _ = winreg.QueryValueEx(registry_key, WINDOWS_LONG_PATHS_REG_VALUE)
    except OSError:
        return None

    return bool(value)
