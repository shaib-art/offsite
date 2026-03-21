from __future__ import annotations

import argparse
from pathlib import Path

from offsite.core.state.db import initialize_database


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="offsite")
    subparsers = parser.add_subparsers(dest="command")

    init_home = subparsers.add_parser("init-home", help="Initialize local state DB")
    init_home.add_argument(
        "--db",
        type=Path,
        default=Path(".offsite/state.db"),
        help="Path to SQLite DB file",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init-home":
        initialize_database(args.db)
        print(f"Initialized state DB at {args.db}")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
