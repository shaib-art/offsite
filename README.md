# offsite

A local-first backup application for managing and verifying personal drive archives,
designed around a one-drive-at-a-time workflow (home ↔ office HDD rotation).

---

## Table of Contents

- [Overview](#overview)
- [Getting started](#getting-started)
- [Usage](#usage)
- [Architecture](#architecture)
- [Developer guide](#developer-guide)
- [Implementation state](#implementation-state)

---

## Overview

`offsite` scans source roots, records file metadata in a local SQLite state database,
and builds deterministic diff/assignment plans for one-drive-at-a-time offline
backup rotation.

Key design constraints:

- **One drive at a time** — no simultaneous multi-drive operations assumed.
- **Local-first** — all state lives in a portable SQLite file; no cloud dependency at runtime.
- **Integrity-first** — checksums are treated as safety-critical; they are never skipped.
- **Cross-platform** — runs on macOS and Windows; Windows long-path (`\\?\`) handling built-in.

---

## Getting started

### Requirements

- Python 3.13+
- No third-party runtime dependencies (Phase 1).

### Setup

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements_dev.txt
export PYTHONPATH=src          # Windows: set PYTHONPATH=src
```

### Initialise the state database

```bash
offsite init-home --db .offsite/state.db
```

---

## Usage

### `init-home` — initialise local state database

```text
offsite init-home [--db PATH]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--db` | `.offsite/state.db` | Path to the SQLite state file |

Creates the directory and bootstraps the schema if the file does not exist (idempotent).

---

### `scan` — snapshot a source root

```text
offsite scan --source PATH [--db PATH] [--include FOLDER ...] [--exclude FOLDER ...]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--source` | *(required)* | Directory root to scan |
| `--db` | `.offsite/state.db` | Path to the SQLite state file |
| `--include FOLDER` | *(none → all)* | Include only this folder (relative to source root; repeatable) |
| `--exclude FOLDER` | *(none)* | Exclude this folder (relative to source root; repeatable) |

Initialises the database if it does not exist, then records all matched files and directories
as a `snapshot_run` row (`running → ok` on success, `running → failed` on error).

**Include/exclude precedence:** the most-specific rule wins (deeper path depth beats shallower).
A tie goes to exclude. An `--include` can create a nested exception inside an `--excluded` ancestor.

**Exit codes:** `0` on success, `1` on scan failure or no subcommand given.

---

### `plan` — build diff + drive assignment plan

```text
offsite plan --snapshot-id ID [--from ID] [--drives LABEL:SIZE,...] [--db PATH]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--snapshot-id` | *(required)* | New snapshot id to plan from |
| `--from` | *(auto previous snapshot)* | Explicit old snapshot id |
| `--drives` | *(none)* | Override persisted inventory with `LABEL:SIZE` CSV |
| `--db` | `.offsite/state.db` | Path to the SQLite state file |

Plan behavior:

- Uses persisted home inventory by default (latest synced office apply result).
- Fails fast when sync/inventory state is stale or missing.
- Applies drive reserve policy per drive: `max(10 GiB, 2% of capacity)`.
- Produces machine-parseable JSON output (`diff_summary`, `allocation`, totals).

---

## Architecture

```text
src/offsite/
├── cli.py                      # Argument parsing and subcommand dispatch
└── core/
    ├── pathing.py              # Cross-platform path utilities (Windows long-path)
  ├── diff/
  │   ├── deleted.py          # Deletion retention helpers
  │   └── differ.py           # Snapshot-to-snapshot diff generation
  ├── plan/
  │   ├── packer.py           # First-fit decreasing bin packing
  │   └── assigner.py         # Reserve-aware drive assignment planning
    ├── scan/
    │   ├── filtering.py        # Include/exclude folder rule matching
    │   ├── scanner.py          # Recursive filesystem traversal
    │   └── snapshot.py         # Scan → persist lifecycle orchestration
    └── state/
        ├── db.py               # SQLite schema bootstrap
    └── repository.py       # snapshot/history/inventory persistence APIs
```

### SQLite schema (Phase 2)

**`snapshot_run`** — one row per scan invocation

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | Auto-increment |
| `started_at` | TEXT | ISO-8601 UTC |
| `finished_at` | TEXT | NULL while running |
| `status` | TEXT | `running` → `ok` or `failed` |
| `source_root` | TEXT | Absolute resolved path |
| `notes` | TEXT | Error message on failure |

**`snapshot_file`** — one row per scanned entry

| Column | Type | Notes |
|--------|------|-------|
| `snapshot_id` | INTEGER FK | References `snapshot_run.id` |
| `path_rel` | TEXT | POSIX-style relative to source root |
| `size_bytes` | INTEGER | |
| `mtime_ns` | INTEGER | Nanosecond mtime |
| `file_type` | TEXT | `file` or `dir` |
| `hash_sha256` | TEXT | Reserved for integrity phases |

**`office_apply_result`** — latest office-side apply synchronization marker

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | Auto-increment |
| `applied_snapshot_id` | INTEGER FK | References `snapshot_run.id` |
| `applied_at` | TEXT | ISO-8601 UTC |

**`home_drive_inventory`** — persisted home-side drive inventory snapshot

| Column | Type | Notes |
|--------|------|-------|
| `drive_label` | TEXT | Stable drive label |
| `capacity_bytes` | INTEGER | Total capacity |
| `free_bytes` | INTEGER | Current free bytes |
| `apply_result_id` | INTEGER FK | References `office_apply_result.id` |

---

## Developer guide

### Running tests

```bash
# All tests
.venv/bin/pytest -q

# With coverage
.venv/bin/pytest --cov=src/offsite --cov-report=term-missing -q
```

### Running lint and type checks

```bash
# Python lint + typing + docs + YAML
.venv/bin/tox -e lint,type,lint-docs,lint-yaml
```

### Coverage gates

| Scope | Minimum |
|-------|---------|
| Overall | 85% |
| Critical modules (scan, plan, apply, integrity) | 90% |

### Coding conventions

- `pathlib.Path`-first APIs — no `str | Path` signatures unless forced by third-party.
- KISS + single responsibility; minimal nesting; guard clauses over nested conditionals.
- Design patterns only when they clearly reduce complexity.
- All test sample strings use **Monty Python** Flying Circus / film script themes.

### TDD workflow (mandatory)

1. Write failing tests and commit (`phase1(iterationN): add failing …`).
2. Write minimal code to pass, commit (`phase1(iterationN): implement …`).
3. Optional refactor commit if needed.
4. Between-iteration housekeeping commits use the `review:` prefix.

### CI matrix (GitHub Actions)

- `lint-and-types` (ubuntu-latest)
- `unit-tests` (ubuntu-latest, windows-latest)
- `coverage-gate` (ubuntu-latest)
- Additional meta lint: `super-linter` job for Markdown, GitHub Actions, YAML, and JSON files

---

## Implementation state

> **Read this section first when resuming in a new session.**

### Current branch

- Branch: `main`
- Phase 2 implementation merged

### Phase 2 — Diff planning and drive assignment

**Delivered scope:** deterministic snapshot diffing, deletion-retention gating,
reserve-aware drive assignment planning, inventory-backed `plan` CLI, and CI
quality/coverage enforcement.

#### Completed iterations

| # | Scope | Status |
|---|-------|--------|
| 1 | Diff generation foundation | COMPLETE |
| 2 | Deletion retention and deletable gate | COMPLETE |
| 3 | Packing/assignment over heterogeneous drives | COMPLETE |
| 4 | `plan` CLI wiring + inventory-first behavior | COMPLETE |
| 5 | Edge-case hardening + phase-module confidence | COMPLETE |
| 6 | CI expansion + simulation coverage evolution | COMPLETE |

#### Current test / coverage snapshot

- **77 tests passing**, 0 failures
- **92.34% overall coverage** (gate >=85%)
- **95.89% phase-module coverage** for `offsite.core.diff` + `offsite.core.plan` (gate >=90%)

#### Key implemented policy decisions

- CLI framework verdict: keep `argparse` for Phase 2.
- Planning reserve policy: `max(10 GiB, 2% capacity)` per drive (non-overridable).
- Planning default: persisted inventory first; explicit `--drives` remains override.
- CI cleanup: PR-only workflow triggers; static analysis deduplicated to single OS;
  cross-OS runtime tests retained.

#### Pending / next steps (Phase 3 candidates)

- Apply/copy execution pipeline based on generated plan.
- Integrity hashing/verification lifecycle (`hash_sha256` activation).
- Restore/reconciliation workflows and failure recovery UX.
