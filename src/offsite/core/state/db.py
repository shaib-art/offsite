"""SQLite bootstrap and schema initialization helpers."""

from __future__ import annotations

import sqlite3
import warnings
from contextlib import closing
from pathlib import Path

from offsite.core.pathing import get_windows_long_path_warning, to_windows_extended_path

SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS snapshot_run (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    source_root TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS snapshot_file (
    snapshot_id INTEGER NOT NULL,
    path_rel TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    file_type TEXT NOT NULL,
    hash_sha256 TEXT,
    FOREIGN KEY (snapshot_id) REFERENCES snapshot_run(id)
);

CREATE TABLE IF NOT EXISTS office_apply_result (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    applied_snapshot_id INTEGER NOT NULL,
    applied_at TEXT NOT NULL,
    apply_run_id TEXT,
    source_plan_id TEXT,
    uploaded_run_id TEXT,
    completed_at TEXT,
    envelope_sha256 TEXT,
    FOREIGN KEY (applied_snapshot_id) REFERENCES snapshot_run(id)
);

CREATE TABLE IF NOT EXISTS home_drive_inventory (
    drive_label TEXT NOT NULL,
    capacity_bytes INTEGER NOT NULL,
    free_bytes INTEGER NOT NULL,
    apply_result_id INTEGER NOT NULL,
    PRIMARY KEY (drive_label, apply_result_id),
    FOREIGN KEY (apply_result_id) REFERENCES office_apply_result(id)
);

CREATE TABLE IF NOT EXISTS placement_index (
    path_rel TEXT PRIMARY KEY,
    drive_label TEXT NOT NULL,
    version_token TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    apply_result_id INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (apply_result_id) REFERENCES office_apply_result(id)
);

CREATE TABLE IF NOT EXISTS workflow_checkpoint (
    workflow_kind TEXT NOT NULL,
    checkpoint_key TEXT NOT NULL,
    run_id TEXT NOT NULL,
    step_index INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (workflow_kind, checkpoint_key)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_office_apply_result_run_id
ON office_apply_result (apply_run_id)
WHERE apply_run_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_office_apply_result_envelope_sha256
ON office_apply_result (envelope_sha256)
WHERE envelope_sha256 IS NOT NULL;
"""

ALLOWED_MIGRATION_TABLES = {
    "snapshot_run",
    "snapshot_file",
    "office_apply_result",
    "home_drive_inventory",
    "placement_index",
    "workflow_checkpoint",
}

ALLOWED_MIGRATION_COLUMNS = {
    "office_apply_result": {
        "apply_run_id",
        "source_plan_id",
        "uploaded_run_id",
        "completed_at",
        "envelope_sha256",
    }
}

ALLOWED_COLUMN_TYPES = {
    "TEXT",
    "INTEGER",
    "REAL",
    "BLOB",
    "NUMERIC",
}


def initialize_database(db_path: Path) -> None:
    """Initialize the phase-1 SQLite schema at the requested path."""
    database_path = db_path.resolve()
    database_path.parent.mkdir(parents=True, exist_ok=True)

    warning_text = get_windows_long_path_warning(database_path)
    if warning_text:
        warnings.warn(warning_text, RuntimeWarning, stacklevel=2)

    connect_path = to_windows_extended_path(database_path)
    with closing(sqlite3.connect(connect_path)) as conn:
        conn.executescript(SCHEMA_V1)
        _migrate_schema(conn)
        conn.commit()


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Apply forward-only additive schema migrations for existing DBs."""
    _ensure_column(conn, "office_apply_result", "apply_run_id", "TEXT")
    _ensure_column(conn, "office_apply_result", "source_plan_id", "TEXT")
    _ensure_column(conn, "office_apply_result", "uploaded_run_id", "TEXT")
    _ensure_column(conn, "office_apply_result", "completed_at", "TEXT")
    _ensure_column(conn, "office_apply_result", "envelope_sha256", "TEXT")

    # Keep this DDL aligned with SCHEMA_V1 on purpose: fresh installs use the
    # canonical schema, while existing DBs rely on this idempotent block during
    # forward migration.
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS placement_index (
            path_rel TEXT PRIMARY KEY,
            drive_label TEXT NOT NULL,
            version_token TEXT NOT NULL,
            content_sha256 TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            apply_result_id INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (apply_result_id) REFERENCES office_apply_result(id)
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_office_apply_result_run_id
        ON office_apply_result (apply_run_id)
        WHERE apply_run_id IS NOT NULL;

        CREATE UNIQUE INDEX IF NOT EXISTS idx_office_apply_result_envelope_sha256
        ON office_apply_result (envelope_sha256)
        WHERE envelope_sha256 IS NOT NULL;

        CREATE TABLE IF NOT EXISTS workflow_checkpoint (
            workflow_kind TEXT NOT NULL,
            checkpoint_key TEXT NOT NULL,
            run_id TEXT NOT NULL,
            step_index INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (workflow_kind, checkpoint_key)
        );
        """
    )


def _ensure_column(
    conn: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_type: str,
) -> None:
    """Add table column when missing to support additive schema evolution."""
    if table_name not in ALLOWED_MIGRATION_TABLES:
        raise ValueError(f"Unsupported migration table: {table_name}")

    allowed_columns = ALLOWED_MIGRATION_COLUMNS.get(table_name, set())
    if column_name not in allowed_columns:
        raise ValueError(
            f"Unsupported migration column {column_name!r} for table {table_name!r}"
        )

    normalized_column_type = column_type.upper()
    if normalized_column_type not in ALLOWED_COLUMN_TYPES:
        raise ValueError(f"Unsupported migration column type: {column_type}")

    existing_columns = {
        str(row[1])
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name in existing_columns:
        return
    conn.execute(
        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {normalized_column_type}"
    )
