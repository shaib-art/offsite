import sqlite3

from offsite.cli import main


def test_init_home_creates_database_file(tmp_path):
    db_path = tmp_path / "state.db"

    exit_code = main(["init-home", "--db", str(db_path)])

    assert exit_code == 0
    assert db_path.exists()

    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "snapshot_run" in tables
    assert "snapshot_file" in tables
