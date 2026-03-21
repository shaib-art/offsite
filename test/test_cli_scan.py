"""CLI tests for the scan subcommand."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from offsite.cli import main
from offsite.core.scan.snapshot import SnapshotRunResult


def test_scan_exits_zero_on_success(tmp_path):
    """scan against a valid source root should return exit code 0."""
    source = tmp_path / "ministry_of_silly_walks"
    source.mkdir()
    (source / "spanish_inquisition.txt").write_text("Nobody expects it!")
    db = tmp_path / "state.db"

    exit_code = main(["scan", "--source", str(source), "--db", str(db)])

    assert exit_code == 0


def test_scan_prints_run_id_in_output(tmp_path, capsys):
    """scan should print a summary line containing 'run_id' on success."""
    source = tmp_path / "camelot"
    source.mkdir()
    db = tmp_path / "state.db"

    main(["scan", "--source", str(source), "--db", str(db)])

    captured = capsys.readouterr()
    assert "run_id" in captured.out


def test_scan_returns_nonzero_when_run_fails(tmp_path):
    """scan should return a non-zero exit code when the snapshot run is marked failed."""
    fake_result = SnapshotRunResult(run_id=42, status="failed")
    source = tmp_path / "swamp_castle"
    source.mkdir()
    db = tmp_path / "state.db"

    with patch("offsite.cli.execute_snapshot_run", return_value=fake_result):
        exit_code = main(["scan", "--source", str(source), "--db", str(db)])

    assert exit_code != 0


def test_scan_forwards_include_and_exclude_flags(tmp_path):
    """scan should pass --include and --exclude path lists to execute_snapshot_run."""
    fake_result = SnapshotRunResult(run_id=1, status="ok")
    source = tmp_path / "black_knight"
    source.mkdir()
    db = tmp_path / "state.db"

    with patch("offsite.cli.execute_snapshot_run", return_value=fake_result) as mock_run:
        main([
            "scan",
            "--source", str(source),
            "--db", str(db),
            "--include", "arm",
            "--exclude", "leg",
        ])

    mock_run.assert_called_once()
    kwargs = mock_run.call_args.kwargs
    assert kwargs["include_folders"] == [Path("arm")]
    assert kwargs["exclude_folders"] == [Path("leg")]
