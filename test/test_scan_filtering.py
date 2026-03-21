"""Tests for include/exclude folder filtering and scan summary counters."""

from pathlib import Path

from offsite.core.scan.scanner import scan_source


def test_include_rule_scans_only_selected_subtree(tmp_path: Path):
    """Include rules should limit scanning to the selected subtree."""
    (tmp_path / "castle_aaaargh").mkdir()
    (tmp_path / "castle_aaaargh" / "grail.txt").write_text("bring out your dead", encoding="utf-8")
    (tmp_path / "ministry_of_silly_walks").mkdir()
    (tmp_path / "ministry_of_silly_walks" / "report.txt").write_text("ni", encoding="utf-8")

    result = scan_source(tmp_path, include_folders=[Path("castle_aaaargh")])

    path_rels = [entry["path_rel"] for entry in result.entries]
    assert "castle_aaaargh" in path_rels
    assert "castle_aaaargh/grail.txt" in path_rels
    assert "ministry_of_silly_walks" not in path_rels
    assert "ministry_of_silly_walks/report.txt" not in path_rels



def test_exclude_rule_skips_entire_subtree(tmp_path: Path):
    """Exclude rules should skip matching folders and their descendants."""
    (tmp_path / "bridge_of_death").mkdir()
    (tmp_path / "bridge_of_death" / "keeper.txt").write_text("what is your quest", encoding="utf-8")
    (tmp_path / "camelot").mkdir()
    (tmp_path / "camelot" / "knights.txt").write_text("we dine well here", encoding="utf-8")

    result = scan_source(tmp_path, exclude_folders=[Path("bridge_of_death")])

    path_rels = [entry["path_rel"] for entry in result.entries]
    assert "camelot" in path_rels
    assert "camelot/knights.txt" in path_rels
    assert "bridge_of_death" not in path_rels
    assert "bridge_of_death/keeper.txt" not in path_rels



def test_include_exclude_precedence_is_deterministic(tmp_path: Path):
    """When a path matches both lists, exclude takes precedence."""
    (tmp_path / "black_knight").mkdir()
    (tmp_path / "black_knight" / "stump.txt").write_text("tis but a scratch", encoding="utf-8")

    result = scan_source(
        tmp_path,
        include_folders=[Path("black_knight")],
        exclude_folders=[Path("black_knight")],
    )

    path_rels = [entry["path_rel"] for entry in result.entries]
    assert "black_knight" not in path_rels
    assert "black_knight/stump.txt" not in path_rels


def test_excluded_base_can_contain_explicitly_included_nested_subtree(tmp_path: Path):
    """Traversal should allow include exceptions nested under an excluded base folder."""
    (tmp_path / "spam").mkdir()
    (tmp_path / "spam" / "holy_grail").mkdir()
    (tmp_path / "spam" / "holy_grail" / "cave").mkdir()
    (tmp_path / "spam" / "holy_grail" / "cave" / "rabbit.txt").write_text(
        "run away",
        encoding="utf-8",
    )

    result = scan_source(
        tmp_path,
        include_folders=[Path("spam/holy_grail/cave")],
        exclude_folders=[Path("spam")],
    )

    path_rels = [entry["path_rel"] for entry in result.entries]
    assert "spam" not in path_rels
    assert "spam/holy_grail" not in path_rels
    assert "spam/holy_grail/cave" in path_rels
    assert "spam/holy_grail/cave/rabbit.txt" in path_rels


def test_scan_summary_counters_track_scanned_included_and_excluded(tmp_path: Path):
    """Scan summary counters should report scanned/included/excluded totals."""
    (tmp_path / "holy_grail").mkdir()
    (tmp_path / "holy_grail" / "map.txt").write_text("seek the grail", encoding="utf-8")
    (tmp_path / "spam").mkdir()
    (tmp_path / "spam" / "spam.txt").write_text("spam spam spam", encoding="utf-8")

    result = scan_source(tmp_path, include_folders=[Path("holy_grail")])

    assert result.scanned_count >= 3
    assert result.included_count == len(result.entries)
    assert result.excluded_count >= 1
