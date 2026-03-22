"""Command-line entry points for phase-1 offsite operations."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

from offsite.core.diff.differ import Differ
from offsite.core.plan.assigner import Assigner, DriveInfo
from offsite.core.plan.packer import DriveAllocation
from offsite.core.scan.snapshot import execute_snapshot_run
from offsite.core.state.db import initialize_database
from offsite.core.state.repository import SnapshotRepository


def build_parser() -> argparse.ArgumentParser:
    """Build the root CLI parser and subcommands."""
    parser = argparse.ArgumentParser(prog="offsite")
    subparsers = parser.add_subparsers(dest="command")

    init_home = subparsers.add_parser("init-home", help="Initialize local state DB")
    init_home.add_argument(
        "--db",
        type=Path,
        default=Path(".offsite/state.db"),
        help="Path to SQLite DB file",
    )

    scan = subparsers.add_parser("scan", help="Run a source-root snapshot scan")
    scan.add_argument("--source", type=Path, required=True, help="Source root to scan")
    scan.add_argument(
        "--db",
        type=Path,
        default=Path(".offsite/state.db"),
        help="Path to SQLite DB file",
    )
    scan.add_argument(
        "--include",
        type=Path,
        action="append",
        dest="include_folders",
        metavar="FOLDER",
        help="Include folder relative to source root (can repeat)",
    )
    scan.add_argument(
        "--exclude",
        type=Path,
        action="append",
        dest="exclude_folders",
        metavar="FOLDER",
        help="Exclude folder relative to source root (can repeat)",
    )

    plan = subparsers.add_parser("plan", help="Build a diff + drive assignment plan")
    plan.add_argument(
        "--snapshot-id",
        type=int,
        required=True,
        help="New snapshot id to plan from",
    )
    plan.add_argument(
        "--from",
        dest="from_snapshot_id",
        type=int,
        help="Optional explicit old snapshot id",
    )
    plan.add_argument(
        "--drives",
        help="Comma-separated drive specs like Office-01:500GB,Office-02:500GB",
    )
    plan.add_argument(
        "--db",
        type=Path,
        default=Path(".offsite/state.db"),
        help="Path to SQLite DB file",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Execute the CLI command and return a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init-home":
        initialize_database(args.db)
        print(f"Initialized state DB at {args.db}")
        return 0

    if args.command == "scan":
        initialize_database(args.db)
        result = execute_snapshot_run(
            db_path=args.db,
            source_root=args.source,
            include_folders=args.include_folders,
            exclude_folders=args.exclude_folders,
        )
        if result.status == "ok":
            print(f"Scan complete: run_id={result.run_id}")
            return 0
        print(f"Scan failed: run_id={result.run_id}", file=sys.stderr)
        return 1

    if args.command == "plan":
        initialize_database(args.db)
        try:
            payload = _build_plan_payload(
                db_path=args.db,
                new_snapshot_id=args.snapshot_id,
                from_snapshot_id=args.from_snapshot_id,
                drive_spec=args.drives,
            )
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1

        print(json.dumps(payload))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())


def _build_plan_payload(
    db_path: Path,
    new_snapshot_id: int,
    from_snapshot_id: int | None,
    drive_spec: str,
) -> dict:
    """Build a machine-parseable plan payload from snapshots and drive specs."""

    with closing(sqlite3.connect(db_path.resolve())) as connection:
        repository = SnapshotRepository(connection)
        drives = _resolve_planning_drives(repository=repository, drive_spec=drive_spec)
        old_snapshot_id = _resolve_snapshot_range(
            repository=repository,
            new_snapshot_id=new_snapshot_id,
            from_snapshot_id=from_snapshot_id,
        )

        differ = Differ(repository)
        diff_entries = differ.diff(old_snapshot_id=old_snapshot_id, new_snapshot_id=new_snapshot_id)

    assigner = Assigner()
    plan = assigner.assign(diff_entries=diff_entries, available_drives=drives)
    summary = {"added": 0, "modified": 0, "deleted": 0, "unchanged": 0}
    for entry in diff_entries:
        summary[entry.kind] += 1

    return {
        "new_snapshot_id": str(new_snapshot_id),
        "old_snapshot_id": str(old_snapshot_id),
        "diff_summary": summary,
        "allocation": _build_allocation_payload(plan.allocations, drives),
        "total_files_to_allocate": plan.total_files,
        "total_bytes_allocated": plan.total_size_bytes,
    }


def _resolve_snapshot_range(
    repository: SnapshotRepository,
    new_snapshot_id: int,
    from_snapshot_id: int | None,
) -> int:
    """Resolve old/new snapshot ids and validate both rows exist."""
    if not repository.snapshot_exists(new_snapshot_id):
        raise ValueError(f"Snapshot id {new_snapshot_id} does not exist")

    old_snapshot_id = from_snapshot_id
    if old_snapshot_id is None:
        old_snapshot_id = repository.get_previous_snapshot_id(new_snapshot_id)
    if old_snapshot_id is None:
        raise ValueError("No previous snapshot available; pass --from explicitly")
    if not repository.snapshot_exists(old_snapshot_id):
        raise ValueError(f"Snapshot id {old_snapshot_id} does not exist")
    return old_snapshot_id


def _build_allocation_payload(
    allocations: list[DriveAllocation],
    drives: list[DriveInfo],
) -> list[dict[str, object]]:
    """Build allocation rows with human-readable labels and file lists."""
    drive_labels = {drive.index: drive.label for drive in drives}
    return [
        {
            "drive_label": drive_labels[allocation.drive_index],
            "file_count": len(allocation.files),
            "size_bytes": allocation.total_size_bytes,
            "files": [path.as_posix() for path in allocation.files],
        }
        for allocation in allocations
    ]


def _parse_drive_spec(drive_spec: str) -> list[DriveInfo]:
    """Parse comma-separated drive labels and size units into DriveInfo rows."""
    items = [item.strip() for item in drive_spec.split(",") if item.strip()]
    if not items:
        raise ValueError("Invalid drive spec: expected at least one drive")

    drives: list[DriveInfo] = []
    for index, item in enumerate(items):
        if ":" not in item:
            raise ValueError("Invalid drive spec: expected LABEL:SIZE entries")
        label, size_text = item.split(":", 1)
        label = label.strip()
        size_text = size_text.strip()
        if not label or not size_text:
            raise ValueError("Invalid drive spec: expected LABEL:SIZE entries")
        size_bytes = _parse_size_bytes(size_text)
        drives.append(
            DriveInfo(
                index=index,
                label=label,
                capacity_bytes=size_bytes,
                free_bytes=size_bytes,
            )
        )
    return drives


def _resolve_planning_drives(
    repository: SnapshotRepository,
    drive_spec: str | None,
) -> list[DriveInfo]:
    """Resolve drives from explicit override or synced home inventory state."""
    override_drives: list[DriveInfo] | None = None
    if drive_spec is not None:
        override_drives = _parse_drive_spec(drive_spec)

    latest_apply_result_id = repository.get_latest_office_apply_result_id()
    if latest_apply_result_id is None:
        raise ValueError(
            "Home state is missing office apply sync; sync latest office apply result before planning"
        )

    inventory_rows = repository.get_home_drive_inventory(latest_apply_result_id)
    if not inventory_rows:
        raise ValueError(
            "Home inventory is stale or missing for latest office apply result; sync inventory before planning"
        )

    if override_drives is not None:
        return override_drives

    return [
        DriveInfo(
            index=index,
            label=row.drive_label,
            capacity_bytes=row.capacity_bytes,
            free_bytes=row.free_bytes,
        )
        for index, row in enumerate(inventory_rows)
    ]


def _parse_size_bytes(size_text: str) -> int:
    """Parse a size token (e.g. 500GB, 100B) into integer bytes."""
    match = re.fullmatch(r"(\d+)([A-Za-z]+)", size_text)
    if match is None:
        raise ValueError("Invalid drive spec: unsupported size format")

    number = int(match.group(1))
    unit = match.group(2).upper()
    multipliers = {
        "B": 1,
        "KB": 1_000,
        "MB": 1_000_000,
        "GB": 1_000_000_000,
        "TB": 1_000_000_000_000,
    }
    if unit not in multipliers:
        raise ValueError("Invalid drive spec: unsupported size unit")
    if number <= 0:
        raise ValueError("Invalid drive spec: size must be positive")
    return number * multipliers[unit]
