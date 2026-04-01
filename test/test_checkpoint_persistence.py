"""Tests for Phase 4 checkpoint persistence and resume conflict detection."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from offsite.core.state.db import initialize_database
from offsite.core.state.repository import SnapshotRepository


def test_checkpoint_persistence_round_trip(tmp_path: Path) -> None:
    """Checkpoint state should persist and load across connection restarts."""
    db_path = tmp_path / "checkpoint_round_trip.db"
    initialize_database(db_path)

    with closing(sqlite3.connect(db_path)) as connection:
        repository = SnapshotRepository(connection)
        repository.upsert_workflow_checkpoint(
            workflow_kind="recovery",
            checkpoint_key="apply-coconut-001:/restore/home",
            run_id="restore-run-001",
            step_index=2,
            payload_json='{"restored":2}',
        )
        connection.commit()

    with closing(sqlite3.connect(db_path)) as connection:
        repository = SnapshotRepository(connection)
        checkpoint = repository.get_workflow_checkpoint(
            workflow_kind="recovery",
            checkpoint_key="apply-coconut-001:/restore/home",
        )

    assert checkpoint is not None
    assert checkpoint.workflow_kind == "recovery"
    assert checkpoint.checkpoint_key == "apply-coconut-001:/restore/home"
    assert checkpoint.run_id == "restore-run-001"
    assert checkpoint.step_index == 2
    assert checkpoint.payload_json == '{"restored":2}'


def test_checkpoint_resume_allows_same_run_id_update(tmp_path: Path) -> None:
    """Resume updates should be allowed when run identity is unchanged."""
    db_path = tmp_path / "checkpoint_resume.db"
    initialize_database(db_path)

    with closing(sqlite3.connect(db_path)) as connection:
        repository = SnapshotRepository(connection)
        repository.upsert_workflow_checkpoint(
            workflow_kind="recovery",
            checkpoint_key="apply-coconut-001:/restore/home",
            run_id="restore-run-001",
            step_index=1,
            payload_json='{"restored":1}',
        )
        repository.upsert_workflow_checkpoint(
            workflow_kind="recovery",
            checkpoint_key="apply-coconut-001:/restore/home",
            run_id="restore-run-001",
            step_index=3,
            payload_json='{"restored":3}',
        )
        connection.commit()

        checkpoint = repository.get_workflow_checkpoint(
            workflow_kind="recovery",
            checkpoint_key="apply-coconut-001:/restore/home",
        )

    assert checkpoint is not None
    assert checkpoint.step_index == 3
    assert checkpoint.payload_json == '{"restored":3}'


def test_checkpoint_resume_rejects_conflicting_run_id(tmp_path: Path) -> None:
    """Checkpoint upsert should fail closed when run identity conflicts."""
    db_path = tmp_path / "checkpoint_conflict.db"
    initialize_database(db_path)

    with closing(sqlite3.connect(db_path)) as connection:
        repository = SnapshotRepository(connection)
        repository.upsert_workflow_checkpoint(
            workflow_kind="recovery",
            checkpoint_key="apply-coconut-001:/restore/home",
            run_id="restore-run-001",
            step_index=1,
            payload_json='{"restored":1}',
        )

        with pytest.raises(ValueError, match="conflicting checkpoint run_id"):
            repository.upsert_workflow_checkpoint(
                workflow_kind="recovery",
                checkpoint_key="apply-coconut-001:/restore/home",
                run_id="restore-run-002",
                step_index=2,
                payload_json='{"restored":2}',
            )
