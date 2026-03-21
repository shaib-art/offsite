import sqlite3

from offsite.core.state.db import initialize_database


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1] for row in rows}


def test_initialize_database_creates_schema(tmp_path):
    db_path = tmp_path / "state.db"

    initialize_database(db_path)

    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "snapshot_run" in tables
    assert "snapshot_file" in tables


def test_initialize_database_is_idempotent(tmp_path):
    db_path = tmp_path / "state.db"

    initialize_database(db_path)
    initialize_database(db_path)

    with sqlite3.connect(db_path) as conn:
        row_count = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name IN ('snapshot_run', 'snapshot_file')"
        ).fetchone()[0]
    assert row_count == 2


def test_initialize_database_has_required_columns(tmp_path):
    db_path = tmp_path / "state.db"

    initialize_database(db_path)

    with sqlite3.connect(db_path) as conn:
        run_columns = _table_columns(conn, "snapshot_run")
        file_columns = _table_columns(conn, "snapshot_file")

    assert {"id", "started_at", "finished_at", "status", "source_root", "notes"} <= run_columns
    assert {
        "snapshot_id",
        "path_rel",
        "size_bytes",
        "mtime_ns",
        "file_type",
        "hash_sha256",
    } <= file_columns
