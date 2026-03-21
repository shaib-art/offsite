"""CLI tests for init-home behavior and command handling."""

from offsite.cli import main


def test_init_home_creates_database_file(tmp_path, open_sqlite):
    """init-home should create a DB file and bootstrap required tables."""
    db_path = tmp_path / "grail_state.db"

    exit_code = main(["init-home", "--db", str(db_path)])

    assert exit_code == 0
    assert db_path.exists()

    with open_sqlite(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "snapshot_run" in tables
    assert "snapshot_file" in tables


def test_main_without_command_returns_nonzero():
    """CLI should return a failure code when no subcommand is provided."""
    exit_code = main([])
    assert exit_code == 1
