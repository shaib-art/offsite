"""Command-line entry points for phase-1 offsite operations."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from offsite.core.scan.snapshot import execute_snapshot_run
from offsite.core.state.db import initialize_database


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

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
