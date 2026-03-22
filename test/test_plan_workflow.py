"""Integration-style tests for diff and drive assignment planning workflow."""

from __future__ import annotations

from pathlib import Path

from offsite.core.diff.differ import Differ
from offsite.core.plan.assigner import Assigner, DriveInfo
from offsite.core.state.db import initialize_database
from offsite.core.state.repository import SnapshotRepository


GIB = 1024 * 1024 * 1024


def _seed_snapshot(repository: SnapshotRepository, source_root: Path, entries: list[dict]) -> int:
    """Create and complete a snapshot run with provided snapshot_file rows."""
    run_id = repository.create_run_running(source_root)
    repository.insert_snapshot_files(run_id, entries)
    repository.mark_run_ok(run_id)
    return run_id


def test_diff_to_plan_assignment_workflow(open_sqlite, tmp_path: Path) -> None:
    """Changed files should be assigned to drives and deletions excluded from packing."""
    db_path = tmp_path / "plan_workflow.db"
    initialize_database(db_path)

    with open_sqlite(db_path) as connection:
        repository = SnapshotRepository(connection)
        source_root = tmp_path / "ministry_of_silly_walks"

        old_snapshot_id = _seed_snapshot(
            repository,
            source_root,
            [
                {
                    "path_rel": "ministry_of_silly_walks/grail-scripts.tar",
                    "size_bytes": 30,
                    "mtime_ns": 10,
                    "file_type": "file",
                },
                {
                    "path_rel": "ministry_of_silly_walks/holy_hand_grenade.iso",
                    "size_bytes": 50,
                    "mtime_ns": 20,
                    "file_type": "file",
                },
                {
                    "path_rel": "ministry_of_silly_walks/ni-manual.pdf",
                    "size_bytes": 20,
                    "mtime_ns": 30,
                    "file_type": "file",
                },
            ],
        )
        new_snapshot_id = _seed_snapshot(
            repository,
            source_root,
            [
                {
                    "path_rel": "ministry_of_silly_walks/grail-scripts.tar",
                    "size_bytes": 30,
                    "mtime_ns": 10,
                    "file_type": "file",
                },
                {
                    "path_rel": "ministry_of_silly_walks/spamalot.dmg",
                    "size_bytes": 45,
                    "mtime_ns": 40,
                    "file_type": "file",
                },
                {
                    "path_rel": "ministry_of_silly_walks/black_knight.mov",
                    "size_bytes": 55,
                    "mtime_ns": 50,
                    "file_type": "file",
                },
            ],
        )
        connection.commit()

        differ = Differ(repository)
        diff_entries = differ.diff(old_snapshot_id=old_snapshot_id, new_snapshot_id=new_snapshot_id)

    assigner = Assigner()
    drives = [
        DriveInfo(index=0, label="Office-HDD-01", capacity_bytes=500 * GIB, free_bytes=500 * GIB),
        DriveInfo(index=1, label="Office-HDD-02", capacity_bytes=500 * GIB, free_bytes=500 * GIB),
    ]
    plan = assigner.assign(diff_entries=diff_entries, available_drives=drives)

    by_kind = {"added": 0, "modified": 0, "deleted": 0, "unchanged": 0}
    for entry in diff_entries:
        by_kind[entry.kind] += 1

    allocated_paths = [path for allocation in plan.allocations for path in allocation.files]

    assert by_kind == {"added": 2, "modified": 0, "deleted": 2, "unchanged": 1}
    assert plan.total_files == 2
    assert plan.total_size_bytes == 100
    assert plan.drives_needed <= 2
    assert Path("ministry_of_silly_walks/spamalot.dmg") in allocated_paths
    assert Path("ministry_of_silly_walks/black_knight.mov") in allocated_paths
    assert Path("ministry_of_silly_walks/holy_hand_grenade.iso") not in allocated_paths

    total_capacity = sum(drive.capacity_bytes for drive in drives)
    assert plan.total_size_bytes <= total_capacity
