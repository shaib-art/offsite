"""CLI tests for the plan subcommand."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from offsite.cli import main
from offsite.core.state.db import initialize_database
from offsite.core.state.repository import SnapshotRepository


def _seed_snapshot(repository: SnapshotRepository, source_root: Path, entries: list[dict]) -> int:
    """Create and finalize a snapshot row for plan CLI tests."""
    run_id = repository.create_run_running(source_root)
    repository.insert_snapshot_files(run_id, entries)
    repository.mark_run_ok(run_id)
    return run_id


def _seed_apply_and_inventory(
    db_path: Path,
    snapshot_id: int,
    drives: list[tuple[str, int, int]],
) -> None:
    with sqlite3.connect(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO office_apply_result (applied_snapshot_id, applied_at)
            VALUES (?, '2026-03-22T00:00:00+00:00')
            """,
            (snapshot_id,),
        )
        apply_result_id = int(cursor.lastrowid)
        payload = [
            (label, capacity_bytes, free_bytes, apply_result_id)
            for label, capacity_bytes, free_bytes in drives
        ]
        connection.executemany(
            """
            INSERT INTO home_drive_inventory (drive_label, capacity_bytes, free_bytes, apply_result_id)
            VALUES (?, ?, ?, ?)
            """,
            payload,
        )
        connection.commit()


def test_plan_help_shows_usage(capsys) -> None:
    """Plan help should include required command flags."""
    with pytest.raises(SystemExit) as error:
        main(["plan", "--help"])

    captured = capsys.readouterr()
    assert error.value.code == 0
    assert "--snapshot-id" in captured.out
    assert "--drives" in captured.out


def test_plan_uses_previous_snapshot_by_default(open_sqlite, tmp_path: Path, capsys) -> None:
    """When --from is omitted, plan should use latest previous snapshot + persisted inventory."""
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

    _seed_apply_and_inventory(
        db_path,
        snapshot_id=old_snapshot_id,
        drives=[("Office-01", 100, 100)],
    )

    exit_code = main(
        [
            "plan",
            "--db",
            str(db_path),
            "--snapshot-id",
            str(new_snapshot_id),
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["old_snapshot_id"] == str(old_snapshot_id)
    assert payload["new_snapshot_id"] == str(new_snapshot_id)


def test_plan_accepts_explicit_from_snapshot(open_sqlite, tmp_path: Path, capsys) -> None:
    """Plan should honor explicit --from snapshot selection."""
    db_path = tmp_path / "plan_explicit_from.db"
    initialize_database(db_path)
    source_root = tmp_path / "camelot"

    with open_sqlite(db_path) as connection:
        repository = SnapshotRepository(connection)
        oldest = _seed_snapshot(repository, source_root, [])
        _seed_snapshot(
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

    _seed_apply_and_inventory(
        db_path,
        snapshot_id=oldest,
        drives=[("Office-01", 100, 100)],
    )

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
            "Office-Override:100B",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["old_snapshot_id"] == str(oldest)
    assert payload["new_snapshot_id"] == str(new_snapshot_id)


def test_plan_rejects_invalid_drive_spec(tmp_path: Path, capsys) -> None:
    """Invalid drive spec should fail with an actionable hint."""
    db_path = tmp_path / "plan_invalid_drive.db"
    initialize_database(db_path)

    exit_code = main(["plan", "--db", str(db_path), "--snapshot-id", "1", "--drives", "bad-format"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Invalid drive spec" in captured.err


def test_plan_reports_insufficient_capacity(open_sqlite, tmp_path: Path, capsys) -> None:
    """Plan should fail when no drive can fit files requiring allocation."""
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

    _seed_apply_and_inventory(
        db_path,
        snapshot_id=old_snapshot_id,
        drives=[("Office-01", 100, 100)],
    )

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


def test_plan_rejects_exact_fit_when_default_reserve_applies(
    open_sqlite,
    tmp_path: Path,
    capsys,
) -> None:
    """Plan should keep a safety reserve and reject exact free-space consumption."""
    db_path = tmp_path / "plan_exact_fit_reserve.db"
    initialize_database(db_path)
    source_root = tmp_path / "ministry"

    with open_sqlite(db_path) as connection:
        repository = SnapshotRepository(connection)
        old_snapshot_id = _seed_snapshot(repository, source_root, [])
        new_snapshot_id = _seed_snapshot(
            repository,
            source_root,
            [
                {
                    "path_rel": "ministry/exact_fit.bin",
                    "size_bytes": 100,
                    "mtime_ns": 1,
                    "file_type": "file",
                },
            ],
        )
        connection.commit()

    _seed_apply_and_inventory(
        db_path,
        snapshot_id=old_snapshot_id,
        drives=[("Office-01", 100, 100)],
    )

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
    assert "exact_fit.bin" in captured.err


def test_plan_fails_when_inventory_sync_state_is_missing(
    open_sqlite,
    tmp_path: Path,
    capsys,
) -> None:
    """Planning without synced office apply result should fail with actionable message."""
    db_path = tmp_path / "plan_stale_state.db"
    initialize_database(db_path)
    source_root = tmp_path / "holy_grail"

    with open_sqlite(db_path) as connection:
        repository = SnapshotRepository(connection)
        _seed_snapshot(repository, source_root, [])
        new_snapshot_id = _seed_snapshot(
            repository,
            source_root,
            [
                {
                    "path_rel": "holy_grail/new.bin",
                    "size_bytes": 10,
                    "mtime_ns": 1,
                    "file_type": "file",
                },
            ],
        )
        connection.commit()

    exit_code = main([
        "plan",
        "--db",
        str(db_path),
        "--snapshot-id",
        str(new_snapshot_id),
    ])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "sync" in captured.err.lower()
    assert "office apply" in captured.err.lower()


def test_plan_output_is_machine_parseable_json(open_sqlite, tmp_path: Path, capsys) -> None:
    """Plan output should follow a stable JSON schema for later automation."""
    db_path = tmp_path / "plan_json_output.db"
    initialize_database(db_path)
    source_root = tmp_path / "castle_aaaargh"

    with open_sqlite(db_path) as connection:
        repository = SnapshotRepository(connection)
        old_snapshot_id = _seed_snapshot(
            repository,
            source_root,
            [
                {
                    "path_rel": "castle_aaaargh/keep.txt",
                    "size_bytes": 10,
                    "mtime_ns": 1,
                    "file_type": "file",
                },
                {
                    "path_rel": "castle_aaaargh/delete.txt",
                    "size_bytes": 5,
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
                    "path_rel": "castle_aaaargh/keep.txt",
                    "size_bytes": 10,
                    "mtime_ns": 1,
                    "file_type": "file",
                },
                {
                    "path_rel": "castle_aaaargh/add.txt",
                    "size_bytes": 20,
                    "mtime_ns": 2,
                    "file_type": "file",
                },
            ],
        )
        connection.commit()

    _seed_apply_and_inventory(
        db_path,
        snapshot_id=old_snapshot_id,
        drives=[("Office-01", 100, 100)],
    )

    exit_code = main(
        [
            "plan",
            "--db",
            str(db_path),
            "--from",
            str(old_snapshot_id),
            "--snapshot-id",
            str(new_snapshot_id),
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert set(payload) == {
        "new_snapshot_id",
        "old_snapshot_id",
        "diff_summary",
        "allocation",
        "total_files_to_allocate",
        "total_bytes_allocated",
    }
    assert payload["new_snapshot_id"] == str(new_snapshot_id)
    assert payload["old_snapshot_id"] == str(old_snapshot_id)
    assert payload["diff_summary"] == {
        "added": 1,
        "modified": 0,
        "deleted": 1,
        "unchanged": 1,
    }
    assert payload["total_files_to_allocate"] == 1
    assert payload["total_bytes_allocated"] == 20
    assert len(payload["allocation"]) == 1
    assert set(payload["allocation"][0]) == {
        "drive_label",
        "file_count",
        "size_bytes",
        "files",
    }
