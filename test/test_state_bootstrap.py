"""Tests for SQLite schema bootstrap and idempotent setup."""

import sqlite3

import pytest

from offsite.core.state.db import _ensure_column, initialize_database


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1] for row in rows}


def test_initialize_database_creates_schema(tmp_path, open_sqlite):
    """Database initialization should create required state tables."""
    db_path = tmp_path / "ministry_of_silly_walks.db"

    initialize_database(db_path)

    with open_sqlite(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "snapshot_run" in tables
    assert "snapshot_file" in tables
    assert "office_apply_result" in tables
    assert "home_drive_inventory" in tables
    assert "placement_index" in tables
    assert "workflow_checkpoint" in tables


def test_initialize_database_is_idempotent(tmp_path, open_sqlite):
    """Running database initialization twice should keep schema intact."""
    db_path = tmp_path / "lumberjack_song.db"

    initialize_database(db_path)
    initialize_database(db_path)

    with open_sqlite(db_path) as conn:
        row_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM sqlite_master
            WHERE type='table'
              AND name IN ('snapshot_run', 'snapshot_file', 'office_apply_result', 'home_drive_inventory')
            """
        ).fetchone()[0]
        placement_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM sqlite_master
            WHERE type='table'
              AND name = 'placement_index'
            """
        ).fetchone()[0]
        checkpoint_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM sqlite_master
            WHERE type='table'
              AND name = 'workflow_checkpoint'
            """
        ).fetchone()[0]

    assert row_count == 4
    assert placement_count == 1
    assert checkpoint_count == 1


def test_initialize_database_has_required_columns(tmp_path, open_sqlite):
    """Schema should expose required columns for snapshot_run and snapshot_file."""
    db_path = tmp_path / "life_of_brian.db"

    initialize_database(db_path)

    with open_sqlite(db_path) as conn:
        run_columns = _table_columns(conn, "snapshot_run")
        file_columns = _table_columns(conn, "snapshot_file")
        placement_columns = _table_columns(conn, "placement_index")

    assert {"id", "started_at", "finished_at", "status", "source_root", "notes"} <= run_columns
    assert {
        "snapshot_id",
        "path_rel",
        "size_bytes",
        "mtime_ns",
        "file_type",
        "hash_sha256",
    } <= file_columns
    assert {
        "path_rel",
        "drive_label",
        "version_token",
        "content_sha256",
        "size_bytes",
        "apply_result_id",
        "updated_at",
    } <= placement_columns


def test_ensure_column_rejects_unknown_table_name(tmp_path, open_sqlite):
    """Migration helper should reject non-whitelisted table names."""
    db_path = tmp_path / "argument_safety.db"
    initialize_database(db_path)

    with open_sqlite(db_path) as conn:
        with pytest.raises(ValueError, match="Unsupported migration table"):
            _ensure_column(conn, "office_apply_result;DROP TABLE snapshot_run", "x", "TEXT")


def test_ensure_column_rejects_unknown_column_name(tmp_path, open_sqlite):
    """Migration helper should reject non-whitelisted migration columns."""
    db_path = tmp_path / "column_name_safety.db"
    initialize_database(db_path)

    with open_sqlite(db_path) as conn:
        with pytest.raises(ValueError, match="Unsupported migration column"):
            _ensure_column(conn, "office_apply_result", "bad_column", "TEXT")


def test_ensure_column_rejects_unsupported_column_type(tmp_path, open_sqlite):
    """Migration helper should reject unsupported SQL types."""
    db_path = tmp_path / "column_type_safety.db"
    initialize_database(db_path)

    with open_sqlite(db_path) as conn:
        with pytest.raises(ValueError, match="Unsupported migration column type"):
            _ensure_column(conn, "office_apply_result", "apply_run_id", "TEXT;DROP")
