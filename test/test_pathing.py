from pathlib import Path

from offsite.core import pathing


def test_to_windows_extended_path_returns_original_on_non_windows(monkeypatch):
    monkeypatch.setattr(pathing.sys, "platform", "darwin")
    candidate = Path("/tmp/example")

    assert pathing.to_windows_extended_path(candidate) == candidate


def test_to_windows_extended_path_prefixes_drive_paths(monkeypatch):
    monkeypatch.setattr(pathing.sys, "platform", "win32")

    candidate = Path("C:/data/deep/path")
    converted = pathing.to_windows_extended_path(candidate)

    assert str(converted).startswith("\\\\?\\")


def test_to_windows_extended_path_keeps_prefixed_path(monkeypatch):
    monkeypatch.setattr(pathing.sys, "platform", "win32")

    candidate = Path("\\\\?\\C:\\data\\already")
    converted = pathing.to_windows_extended_path(candidate)

    assert converted == candidate


def test_to_windows_extended_path_prefixes_unc_paths(monkeypatch):
    monkeypatch.setattr(pathing.sys, "platform", "win32")

    candidate = Path("\\\\server\\share\\folder")
    converted = pathing.to_windows_extended_path(candidate)

    assert str(converted).startswith("\\\\?\\UNC\\")


def test_get_windows_long_path_warning_not_set_for_short_path(monkeypatch):
    monkeypatch.setattr(pathing.sys, "platform", "win32")
    monkeypatch.setattr(pathing, "_read_windows_long_paths_enabled", lambda: False)

    warning = pathing.get_windows_long_path_warning(Path("C:/short"))

    assert warning is None


def test_get_windows_long_path_warning_when_policy_missing(monkeypatch):
    monkeypatch.setattr(pathing.sys, "platform", "win32")
    monkeypatch.setattr(pathing, "_read_windows_long_paths_enabled", lambda: None)

    long_path = Path("C:/") / ("nested/" * 60)
    warning = pathing.get_windows_long_path_warning(long_path)

    assert warning is not None
    assert "LongPathsEnabled" in warning


def test_get_windows_long_path_warning_suppressed_when_enabled(monkeypatch):
    monkeypatch.setattr(pathing.sys, "platform", "win32")
    monkeypatch.setattr(pathing, "_read_windows_long_paths_enabled", lambda: True)

    long_path = Path("C:/") / ("nested/" * 60)
    warning = pathing.get_windows_long_path_warning(long_path)

    assert warning is None


def test_read_windows_long_paths_enabled_returns_none_without_winreg():
    assert pathing._read_windows_long_paths_enabled() is None
