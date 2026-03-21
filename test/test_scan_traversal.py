from pathlib import Path

import pytest

from offsite.core.scan.scanner import scan_source


def _find_entry(entries: list[dict], path_rel: str) -> dict:
    for entry in entries:
        if entry["path_rel"] == path_rel:
            return entry
    raise AssertionError(f"Entry not found for path_rel={path_rel}")


def test_scan_recurses_nested_directories_and_is_deterministic(tmp_path: Path):
    (tmp_path / "z-dir").mkdir()
    (tmp_path / "a-dir").mkdir()
    (tmp_path / "a-dir" / "child.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "z-dir" / "another.txt").write_text("world", encoding="utf-8")

    result = scan_source(tmp_path)

    assert result.errors == []
    path_rels = [entry["path_rel"] for entry in result.entries]
    assert path_rels == sorted(path_rels)
    assert "a-dir" in path_rels
    assert "a-dir/child.txt" in path_rels
    assert "z-dir" in path_rels
    assert "z-dir/another.txt" in path_rels


def test_scan_captures_required_metadata_for_files_and_directories(tmp_path: Path):
    (tmp_path / "folder").mkdir()
    file_path = tmp_path / "folder" / "data.bin"
    file_path.write_bytes(b"abc")

    result = scan_source(tmp_path)

    folder_entry = _find_entry(result.entries, "folder")
    file_entry = _find_entry(result.entries, "folder/data.bin")

    assert folder_entry["file_type"] == "dir"
    assert isinstance(folder_entry["mtime_ns"], int)

    assert file_entry["file_type"] == "file"
    assert file_entry["size_bytes"] == 3
    assert isinstance(file_entry["mtime_ns"], int)


def test_scan_skips_symlinks_by_default(tmp_path: Path):
    target_file = tmp_path / "target.txt"
    target_file.write_text("target", encoding="utf-8")
    symlink_path = tmp_path / "link.txt"
    symlink_path.symlink_to(target_file)

    result = scan_source(tmp_path)

    path_rels = [entry["path_rel"] for entry in result.entries]
    assert "target.txt" in path_rels
    assert "link.txt" not in path_rels


def test_scan_records_controlled_error_for_unreadable_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    blocked_dir = tmp_path / "blocked"
    blocked_dir.mkdir()

    from offsite.core.scan import scanner as scanner_module

    original_scandir = scanner_module.os.scandir

    def fake_scandir(path: str):
        if Path(path) == blocked_dir:
            raise PermissionError("blocked")
        return original_scandir(path)

    monkeypatch.setattr(scanner_module.os, "scandir", fake_scandir)

    result = scan_source(tmp_path)

    assert len(result.errors) == 1
    assert result.errors[0]["path_rel"] == "blocked"
    assert result.errors[0]["error_type"] == "PermissionError"
