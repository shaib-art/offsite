"""Tests for snapshot diff generation and deterministic ordering."""

from __future__ import annotations

from pathlib import Path

from offsite.core.diff.differ import Differ
from offsite.core.state.db import initialize_database
from offsite.core.state.repository import SnapshotRepository


def _seed_snapshot(repository: SnapshotRepository, source_root: Path, entries: list[dict]) -> int:
    run_id = repository.create_run_running(source_root)
    repository.insert_snapshot_files(run_id, entries)
    repository.mark_run_ok(run_id)
    return run_id


def test_differ_detects_added_deleted_modified_and_unchanged(open_sqlite, tmp_path: Path) -> None:
    """Diff should classify entries across all four change kinds."""
    db_path = tmp_path / "grail_diff.db"
    initialize_database(db_path)

    with open_sqlite(db_path) as connection:
        repository = SnapshotRepository(connection)
        source_root = tmp_path / "castle_aaaargh"

        old_snapshot_id = _seed_snapshot(
            repository,
            source_root,
            [
                {
                    "path_rel": "castle_aaaargh/unchanged_spam.txt",
                    "size_bytes": 10,
                    "mtime_ns": 100,
                    "file_type": "file",
                },
                {
                    "path_rel": "castle_aaaargh/modified_parrot.txt",
                    "size_bytes": 5,
                    "mtime_ns": 200,
                    "file_type": "file",
                },
                {
                    "path_rel": "castle_aaaargh/deleted_knight.txt",
                    "size_bytes": 8,
                    "mtime_ns": 300,
                    "file_type": "file",
                },
            ],
        )

        new_snapshot_id = _seed_snapshot(
            repository,
            source_root,
            [
                {
                    "path_rel": "castle_aaaargh/unchanged_spam.txt",
                    "size_bytes": 10,
                    "mtime_ns": 100,
                    "file_type": "file",
                },
                {
                    "path_rel": "castle_aaaargh/modified_parrot.txt",
                    "size_bytes": 6,
                    "mtime_ns": 200,
                    "file_type": "file",
                },
                {
                    "path_rel": "castle_aaaargh/added_shrubbery.txt",
                    "size_bytes": 12,
                    "mtime_ns": 400,
                    "file_type": "file",
                },
            ],
        )

        connection.commit()
        differ = Differ(repository)

        diff_entries = differ.diff(old_snapshot_id=old_snapshot_id, new_snapshot_id=new_snapshot_id)

    by_kind = {entry.kind: entry for entry in diff_entries if entry.kind != "unchanged"}
    unchanged = [entry for entry in diff_entries if entry.kind == "unchanged"]

    assert by_kind["added"].path == Path("castle_aaaargh/added_shrubbery.txt")
    assert by_kind["added"].previous_size is None
    assert by_kind["added"].previous_mtime_ns is None

    assert by_kind["modified"].path == Path("castle_aaaargh/modified_parrot.txt")
    assert by_kind["modified"].size_bytes == 6
    assert by_kind["modified"].previous_size == 5

    assert by_kind["deleted"].path == Path("castle_aaaargh/deleted_knight.txt")
    assert by_kind["deleted"].size_bytes == 0
    assert by_kind["deleted"].mtime_ns == 0
    assert by_kind["deleted"].previous_size == 8

    assert len(unchanged) == 1
    assert unchanged[0].path == Path("castle_aaaargh/unchanged_spam.txt")


def test_differ_output_is_stably_sorted_by_path(open_sqlite, tmp_path: Path) -> None:
    """Diff output should always be sorted by path for deterministic plans."""
    db_path = tmp_path / "spamalot_sorting.db"
    initialize_database(db_path)

    with open_sqlite(db_path) as connection:
        repository = SnapshotRepository(connection)
        source_root = tmp_path / "ministry_of_silly_walks"

        old_snapshot_id = _seed_snapshot(
            repository,
            source_root,
            [
                {
                    "path_rel": "ministry_of_silly_walks/zulu.txt",
                    "size_bytes": 1,
                    "mtime_ns": 1,
                    "file_type": "file",
                },
            ],
        )
        new_snapshot_id = _seed_snapshot(
            repository,
            source_root,
            [
                {
                    "path_rel": "ministry_of_silly_walks/alpha.txt",
                    "size_bytes": 1,
                    "mtime_ns": 1,
                    "file_type": "file",
                },
                {
                    "path_rel": "ministry_of_silly_walks/zulu.txt",
                    "size_bytes": 1,
                    "mtime_ns": 1,
                    "file_type": "file",
                },
            ],
        )

        connection.commit()
        differ = Differ(repository)
        diff_entries = differ.diff(old_snapshot_id=old_snapshot_id, new_snapshot_id=new_snapshot_id)

    paths = [entry.path.as_posix() for entry in diff_entries]
    assert paths == sorted(paths)
