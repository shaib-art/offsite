"""Tests for Windows path extension and long-path warning helpers."""

from pathlib import Path

from offsite.core import pathing


def test_to_windows_extended_path_returns_original_on_non_windows(monkeypatch):
    """Non-Windows platforms should leave paths unchanged."""
    monkeypatch.setattr(pathing.sys, "platform", "darwin")
    candidate = Path("/tmp/example")

    assert pathing.to_windows_extended_path(candidate) == candidate


def test_to_windows_extended_path_prefixes_drive_paths(monkeypatch):
    """Windows drive paths should be converted to extended-length form."""
    monkeypatch.setattr(pathing.sys, "platform", "win32")

    candidate = Path("C:/data/deep/path")
    converted = pathing.to_windows_extended_path(candidate)

    assert str(converted).startswith("\\\\?\\")


def test_to_windows_extended_path_keeps_prefixed_path(monkeypatch):
    """Already-extended Windows paths should not be modified."""
    monkeypatch.setattr(pathing.sys, "platform", "win32")

    candidate = Path("\\\\?\\C:\\data\\already")
    converted = pathing.to_windows_extended_path(candidate)

    assert converted == candidate


def test_to_windows_extended_path_prefixes_unc_paths(monkeypatch):
    """UNC paths should be converted to the extended UNC prefix form."""
    monkeypatch.setattr(pathing.sys, "platform", "win32")

    candidate = Path("\\\\server\\share\\folder")
    converted = pathing.to_windows_extended_path(candidate)

    assert str(converted).startswith("\\\\?\\UNC\\")


def test_get_windows_long_path_warning_not_set_for_short_path(monkeypatch):
    """Short paths should not trigger a long-path warning."""
    monkeypatch.setattr(pathing.sys, "platform", "win32")
    monkeypatch.setattr(pathing, "_read_windows_long_paths_enabled", lambda: False)

    warning = pathing.get_windows_long_path_warning(Path("C:/short"))

    assert warning is None


def test_get_windows_long_path_warning_when_policy_missing(monkeypatch):
    """Long paths should warn when policy state cannot be confirmed."""
    monkeypatch.setattr(pathing.sys, "platform", "win32")
    monkeypatch.setattr(pathing, "_read_windows_long_paths_enabled", lambda: None)

    long_path = Path("C:/") / ("nested/" * 60)
    warning = pathing.get_windows_long_path_warning(long_path)

    assert warning is not None
    assert "LongPathsEnabled" in warning


def test_get_windows_long_path_warning_suppressed_when_enabled(monkeypatch):
    """Long-path warning should be suppressed when policy is enabled."""
    monkeypatch.setattr(pathing.sys, "platform", "win32")
    monkeypatch.setattr(pathing, "_read_windows_long_paths_enabled", lambda: True)

    long_path = Path("C:/") / ("nested/" * 60)
    warning = pathing.get_windows_long_path_warning(long_path)

    assert warning is None


def test_read_windows_long_paths_enabled_returns_none_without_winreg():
    """Policy lookup should return None on platforms without winreg."""
    assert pathing._read_windows_long_paths_enabled() is None
