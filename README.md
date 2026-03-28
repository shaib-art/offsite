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
| `--drives` | *(none)* | Override drive specs with `LABEL:SIZE` CSV (does not bypass sync/inventory requirement) |
| `--db` | `.offsite/state.db` | Path to the SQLite state file |

Plan behavior:

- Uses persisted home inventory by default (latest synced office apply result).
- When `--drives` is provided, uses the provided drive specifications for planning,
  but still requires a valid synced apply/inventory state.
- Fails fast when sync/inventory state is stale or missing, even when `--drives` is passed.
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
    ├── upload/
    │   └── executor.py         # Retry/resume upload + manifest emission
    ├── integrity/
    │   └── checksum.py         # SHA-256 verification primitives
    ├── apply_sync/
    │   ├── contract.py         # Immutable apply-result envelope
    │   └── ingest.py           # Home-side ingest and state updates
    ├── scan/
    │   ├── filtering.py        # Include/exclude folder rule matching
    │   ├── scanner.py          # Recursive filesystem traversal
    │   └── snapshot.py         # Scan → persist lifecycle orchestration
    └── state/
        ├── db.py               # SQLite schema bootstrap + additive migration
        └── repository.py       # snapshot/history/inventory/placement APIs
```

### SQLite schema (Phase 3)

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

**`office_apply_result`** — office apply sync history and immutable envelope metadata

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | Auto-increment |
| `applied_snapshot_id` | INTEGER FK | References `snapshot_run.id` |
| `applied_at` | TEXT | ISO-8601 UTC |
| `apply_run_id` | TEXT | Immutable apply run id (unique when present) |
| `source_plan_id` | TEXT | Source plan identifier |
| `uploaded_run_id` | TEXT | Related upload run id |
| `completed_at` | TEXT | Office completion timestamp |
| `envelope_sha256` | TEXT | Immutable envelope integrity hash (unique when present) |

**`home_drive_inventory`** — persisted home-side drive inventory snapshot

| Column | Type | Notes |
|--------|------|-------|
| `drive_label` | TEXT | Stable drive label |
| `capacity_bytes` | INTEGER | Total capacity |
| `free_bytes` | INTEGER | Current free bytes |
| `apply_result_id` | INTEGER FK | References `office_apply_result.id`; with `drive_label` forms composite primary key |

**`placement_index`** — current file-to-drive/version mapping state

| Column | Type | Notes |
|--------|------|-------|
| `path_rel` | TEXT PK | Relative file path |
| `drive_label` | TEXT | Current drive label |
| `version_token` | TEXT | Version mapping token from apply result |
| `content_sha256` | TEXT | Content hash for mapping version |
| `size_bytes` | INTEGER | Recorded mapped size |
| `apply_result_id` | INTEGER FK | References `office_apply_result.id` |
| `updated_at` | TEXT | Last ingest timestamp |

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
- Phase 3 implementation merged locally (report generated)

### Phase 3 — Upload and apply-sync pipeline

**Delivered scope:** upload execution with retry/resume and checksum verification,
immutable office apply-result envelope, home ingest updating inventory and placement
index, and stale-ingest guardrails for `plan`.

#### Completed iterations

| # | Scope | Status |
|---|-------|--------|
| 1 | Upload executor with retry/resume + checksum verification | COMPLETE |
| 2 | Immutable apply-result contract and validation | COMPLETE |
| 3 | Home ingest + idempotent state updates | COMPLETE |
| 4 | Plan stale-ingest enforcement + CI critical gate update | COMPLETE |

#### Current test / coverage snapshot

- **91 tests passing**, 0 failures
- **90.55% overall coverage** (gate >=85%)
- **92.65% critical coverage** for `offsite.core.upload` + `offsite.core.apply_sync` + `offsite.core.integrity` (gate >=90%)

#### Key implemented policy decisions

- CLI framework verdict: keep `argparse` for Phase 3.
- Planning reserve policy: `max(10 GiB, 2% capacity)` per drive (non-overridable).
- Planning default: persisted inventory first; explicit `--drives` remains override.
- Upload run IDs are deterministic from plan + source root when not explicitly provided.
- Apply-result envelopes are immutable via embedded `envelope_sha256` integrity hash.

#### Pending / next steps (Phase 4 candidates)

- Restore/recovery workflow contract and replay-safe executor.
- Persistent upload/apply checkpoints for cross-process resume.
- Envelope schema version migration strategy beyond schema v1.
