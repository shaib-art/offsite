"""Tests for scanner traversal, metadata, and warning behavior."""

from pathlib import Path

import pytest

from offsite.core.scan.scanner import scan_source
from offsite.core.state.db import initialize_database


def _find_entry(entries: list[dict], path_rel: str) -> dict:
    for entry in entries:
        if entry["path_rel"] == path_rel:
            return entry
    raise AssertionError(f"Entry not found for path_rel={path_rel}")


def test_scan_recurses_nested_directories_and_is_deterministic(tmp_path: Path):
    """Scanner should recurse directories and emit entries in stable order."""
    (tmp_path / "zoot").mkdir()
    (tmp_path / "camelot").mkdir()
    (tmp_path / "camelot" / "parrot.txt").write_text("ni", encoding="utf-8")
    (tmp_path / "zoot" / "lumberjack.txt").write_text("spam", encoding="utf-8")

    result = scan_source(tmp_path)

    assert result.errors == []
    path_rels = [entry["path_rel"] for entry in result.entries]
    assert path_rels == sorted(path_rels)
    assert "camelot" in path_rels
    assert "camelot/parrot.txt" in path_rels
    assert "zoot" in path_rels
    assert "zoot/lumberjack.txt" in path_rels


def test_scan_captures_required_metadata_for_files_and_directories(tmp_path: Path):
    """Scanner should record required metadata fields for dirs and files."""
    (tmp_path / "dead_parrot").mkdir()
    file_path = tmp_path / "dead_parrot" / "argument.bin"
    file_path.write_bytes(b"ni!")

    result = scan_source(tmp_path)

    folder_entry = _find_entry(result.entries, "dead_parrot")
    file_entry = _find_entry(result.entries, "dead_parrot/argument.bin")

    assert folder_entry["file_type"] == "dir"
    assert isinstance(folder_entry["mtime_ns"], int)

    assert file_entry["file_type"] == "file"
    assert file_entry["size_bytes"] == 3
    assert isinstance(file_entry["mtime_ns"], int)


def test_scan_skips_symlinks_by_default(tmp_path: Path):
    """Scanner should ignore symlink entries when default options are used."""
    target_file = tmp_path / "black_knight.txt"
    target_file.write_text("tis but a scratch", encoding="utf-8")
    symlink_path = tmp_path / "holy_hand_grenade_link.txt"
    symlink_path.symlink_to(target_file)

    result = scan_source(tmp_path)

    path_rels = [entry["path_rel"] for entry in result.entries]
    assert "black_knight.txt" in path_rels
    assert "holy_hand_grenade_link.txt" not in path_rels


def test_scan_records_controlled_error_for_unreadable_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Scanner should report unreadable paths as controlled non-fatal errors."""
    blocked_dir = tmp_path / "bridge_of_death"
    blocked_dir.mkdir()

    from offsite.core.scan import scanner as scanner_module

    original_scandir = scanner_module.os.scandir

    def fake_scandir(path: str):
        if Path(path) == blocked_dir:
            raise PermissionError("none shall pass")
        return original_scandir(path)

    monkeypatch.setattr(scanner_module.os, "scandir", fake_scandir)

    result = scan_source(tmp_path)

    assert len(result.errors) == 1
    assert result.errors[0]["path_rel"] == "bridge_of_death"
    assert result.errors[0]["error_type"] == "PermissionError"


def test_scan_warns_when_long_path_policy_risk_detected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Scanner should emit a runtime warning when long-path policy is at risk."""
    from offsite.core.scan import scanner as scanner_module

    monkeypatch.setattr(
        scanner_module,
        "get_windows_long_path_warning",
        lambda _path: "ni-long-path-warning",
    )

    with pytest.warns(RuntimeWarning, match="ni-long-path-warning"):
        scan_source(tmp_path)


def test_initialize_database_warns_when_long_path_policy_risk_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Database bootstrap should emit a warning when long-path policy is at risk."""
    from offsite.core.state import db as db_module

    monkeypatch.setattr(
        db_module,
        "get_windows_long_path_warning",
        lambda _path: "ni-long-path-warning",
    )

    db_path = tmp_path / "grail_diary.db"
    with pytest.warns(RuntimeWarning, match="ni-long-path-warning"):
        initialize_database(db_path)
