"""CLI tests for plan subcommand and JSON output behavior."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from offsite.cli import main
from offsite.core.state.db import initialize_database
from offsite.core.state.repository import SnapshotRepository


def _seed_snapshot(repository: SnapshotRepository, source_root: Path, entries: list[dict]) -> int:
    """Create and finalize a snapshot run for CLI plan tests."""
    run_id = repository.create_run_running(source_root)
    repository.insert_snapshot_files(run_id, entries)
    repository.mark_run_ok(run_id)
    return run_id


def test_plan_help_shows_usage(capsys) -> None:
    """Plan subcommand should expose the expected CLI flags in help output."""
    with pytest.raises(SystemExit) as error:
        main(["plan", "--help"])

    captured = capsys.readouterr()
    assert error.value.code == 0
    assert "--snapshot-id" in captured.out
    assert "--drives" in captured.out


def test_plan_uses_previous_snapshot_by_default(open_sqlite, tmp_path: Path, capsys) -> None:
    """Without --from, plan should diff against the latest earlier snapshot."""
    db_path = tmp_path / "plan_default_from.db"
    initialize_database(db_path)
    source_root = tmp_path / "ministry_of_silly_walks"

    with open_sqlite(db_path) as connection:
        repository = SnapshotRepository(connection)
        old_snapshot_id = _seed_snapshot(
            repository,
            source_root,
            [
                {
                    "path_rel": "ministry_of_silly_walks/old.txt",
                    "size_bytes": 10,
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
                    "path_rel": "ministry_of_silly_walks/old.txt",
                    "size_bytes": 10,
                    "mtime_ns": 1,
                    "file_type": "file",
                },
                {
                    "path_rel": "ministry_of_silly_walks/new.txt",
                    "size_bytes": 20,
                    "mtime_ns": 2,
                    "file_type": "file",
                },
            ],
        )
        connection.commit()

    exit_code = main(
        [
            "plan",
            "--db",
            str(db_path),
            "--snapshot-id",
            str(new_snapshot_id),
            "--drives",
            "Office-01:100B",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["old_snapshot_id"] == str(old_snapshot_id)
    assert payload["new_snapshot_id"] == str(new_snapshot_id)


def test_plan_accepts_explicit_from_snapshot(open_sqlite, tmp_path: Path, capsys) -> None:
    """Plan should honor explicit --from snapshot range."""
    db_path = tmp_path / "plan_explicit_from.db"
    initialize_database(db_path)
    source_root = tmp_path / "camelot"

    with open_sqlite(db_path) as connection:
        repository = SnapshotRepository(connection)
        oldest = _seed_snapshot(repository, source_root, [])
        old_snapshot_id = _seed_snapshot(
            repository,
            source_root,
            [
                {
                    "path_rel": "camelot/keep.txt",
                    "size_bytes": 10,
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
                    "path_rel": "camelot/keep.txt",
                    "size_bytes": 10,
                    "mtime_ns": 1,
                    "file_type": "file",
                },
            ],
        )
        connection.commit()

    exit_code = main(
        [
            "plan",
            "--db",
            str(db_path),
            "--from",
            str(oldest),
            "--snapshot-id",
            str(new_snapshot_id),
            "--drives",
            "Office-01:100B",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["old_snapshot_id"] == str(oldest)
    assert payload["new_snapshot_id"] == str(new_snapshot_id)
    assert payload["old_snapshot_id"] != str(old_snapshot_id)


def test_plan_rejects_invalid_drive_spec(tmp_path: Path, capsys) -> None:
    """Invalid drive spec should return non-zero with actionable error hint."""
    db_path = tmp_path / "plan_invalid_drive.db"
    initialize_database(db_path)

    exit_code = main(["plan", "--db", str(db_path), "--snapshot-id", "1", "--drives", "bad-format"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Invalid drive spec" in captured.err


def test_plan_reports_insufficient_capacity(open_sqlite, tmp_path: Path, capsys) -> None:
    """Plan should fail cleanly when drive free space cannot fit required files."""
    db_path = tmp_path / "plan_capacity_fail.db"
    initialize_database(db_path)
    source_root = tmp_path / "bridge_of_death"

    with open_sqlite(db_path) as connection:
        repository = SnapshotRepository(connection)
        old_snapshot_id = _seed_snapshot(repository, source_root, [])
        new_snapshot_id = _seed_snapshot(
            repository,
            source_root,
            [
                {
                    "path_rel": "bridge_of_death/too_large.bin",
                    "size_bytes": 200,
                    "mtime_ns": 1,
                    "file_type": "file",
                },
            ],
        )
        connection.commit()

    exit_code = main(
        [
            "plan",
            "--db",
            str(db_path),
            "--from",
            str(old_snapshot_id),
            "--snapshot-id",
            str(new_snapshot_id),
            "--drives",
            "Office-01:100B",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "too_large.bin" in captured.err
