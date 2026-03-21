"""Tests for snapshot run lifecycle, persistence, and rollback behavior."""

from pathlib import Path

from offsite.core.scan.scanner import ScanResult
from offsite.core.scan.snapshot import execute_snapshot_run
from offsite.core.state.db import initialize_database


def _fetch_run_row(open_sqlite, db_path: Path, run_id: int) -> tuple:
    with open_sqlite(db_path) as conn:
        row = conn.execute(
            "SELECT status, started_at, finished_at, notes FROM snapshot_run WHERE id = ?",
            (run_id,),
        ).fetchone()
    assert row is not None
    return row


def test_snapshot_run_sets_running_status_before_scan(open_sqlite, tmp_path: Path):
    """Run status should be persisted as running before scanner execution begins."""
    db_path = tmp_path / "dead_parrot.db"
    source_root = tmp_path / "ministry_of_silly_walks"
    source_root.mkdir()

    initialize_database(db_path)

    observed: dict[str, str] = {}

    def scan_probe(_source_root: Path, **_kwargs) -> ScanResult:
        with open_sqlite(db_path) as conn:
            status = conn.execute(
                "SELECT status FROM snapshot_run ORDER BY id DESC LIMIT 1"
            ).fetchone()[0]
        observed["status"] = status
        return ScanResult(entries=[], errors=[])

    result = execute_snapshot_run(db_path=db_path, source_root=source_root, scan_func=scan_probe)

    assert observed["status"] == "running"
    assert result.status == "ok"


def test_snapshot_run_transitions_to_ok_on_success(open_sqlite, tmp_path: Path):
    """Successful runs should end in ok state with a finished timestamp."""
    db_path = tmp_path / "holy_grail.db"
    source_root = tmp_path / "camelot"
    source_root.mkdir()

    initialize_database(db_path)

    result = execute_snapshot_run(
        db_path=db_path,
        source_root=source_root,
        scan_func=lambda _source_root, **_kwargs: ScanResult(entries=[], errors=[]),
    )

    status, started_at, finished_at, notes = _fetch_run_row(open_sqlite, db_path, result.run_id)

    assert status == "ok"
    assert started_at
    assert finished_at
    assert notes is None


def test_snapshot_run_transitions_to_failed_with_notes_on_scanner_exception(open_sqlite, tmp_path: Path):
    """Scanner exceptions should mark run failed and persist failure metadata."""
    db_path = tmp_path / "spanish_inquisition.db"
    source_root = tmp_path / "bridge_of_death"
    source_root.mkdir()

    initialize_database(db_path)

    def scan_explodes(_source_root: Path, **_kwargs) -> ScanResult:
        raise RuntimeError("nobody expects the spanish inquisition")

    result = execute_snapshot_run(db_path=db_path, source_root=source_root, scan_func=scan_explodes)

    status, _started_at, finished_at, notes = _fetch_run_row(open_sqlite, db_path, result.run_id)

    assert result.status == "failed"
    assert status == "failed"
    assert finished_at
    assert "spanish inquisition" in notes


def test_snapshot_file_rows_are_tied_to_snapshot_id(open_sqlite, tmp_path: Path):
    """Persisted snapshot_file rows should reference the created snapshot_run id."""
    db_path = tmp_path / "black_knight.db"
    source_root = tmp_path / "castle_aaaargh"
    source_root.mkdir()

    initialize_database(db_path)

    entries = [
        {
            "path_rel": "castle_aaaargh",
            "size_bytes": 0,
            "mtime_ns": 1,
            "file_type": "dir",
        },
        {
            "path_rel": "castle_aaaargh/rabbit.txt",
            "size_bytes": 8,
            "mtime_ns": 2,
            "file_type": "file",
        },
    ]

    result = execute_snapshot_run(
        db_path=db_path,
        source_root=source_root,
        scan_func=lambda _source_root, **_kwargs: ScanResult(entries=entries, errors=[]),
    )

    with open_sqlite(db_path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM snapshot_file WHERE snapshot_id = ?",
            (result.run_id,),
        ).fetchone()[0]

    assert count == 2


def test_snapshot_file_insert_is_rollback_safe_on_persistence_error(open_sqlite, tmp_path: Path):
    """Partial file inserts should roll back and still mark the run as failed."""
    db_path = tmp_path / "holy_hand_grenade.db"
    source_root = tmp_path / "swamp_castle"
    source_root.mkdir()

    initialize_database(db_path)

    invalid_entries = [
        {
            "path_rel": "swamp_castle",
            "size_bytes": 0,
            "mtime_ns": 1,
            "file_type": "dir",
        },
        {
            "path_rel": "swamp_castle/blueprint.txt",
            "mtime_ns": 2,
            "file_type": "file",
        },
    ]

    result = execute_snapshot_run(
        db_path=db_path,
        source_root=source_root,
        scan_func=lambda _source_root, **_kwargs: ScanResult(entries=invalid_entries, errors=[]),
    )

    status, _started_at, _finished_at, notes = _fetch_run_row(open_sqlite, db_path, result.run_id)

    with open_sqlite(db_path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM snapshot_file WHERE snapshot_id = ?",
            (result.run_id,),
        ).fetchone()[0]

    assert result.status == "failed"
    assert status == "failed"
    assert count == 0
    assert "size_bytes" in notes
