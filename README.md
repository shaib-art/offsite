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
and (in later phases) verifies integrity across backup drives and cloud targets.

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

## Architecture

```text
src/offsite/
├── cli.py                      # Argument parsing and subcommand dispatch
└── core/
    ├── pathing.py              # Cross-platform path utilities (Windows long-path)
    ├── scan/
    │   ├── filtering.py        # Include/exclude folder rule matching
    │   ├── scanner.py          # Recursive filesystem traversal
    │   └── snapshot.py         # Scan → persist lifecycle orchestration
    └── state/
        ├── db.py               # SQLite schema bootstrap
        └── repository.py       # snapshot_run / snapshot_file persistence
```

### SQLite schema (Phase 1)

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
| `hash_sha256` | TEXT | NULL in Phase 1 (reserved for Phase 2) |

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

- `lint-and-types`, `unit-tests`, `simulation-tests`, `coverage-gate`
- Platforms: `ubuntu-latest`, `windows-latest`
- Additional meta lint: `super-linter` job for Markdown, GitHub Actions, YAML, and JSON files

---

## Implementation state

> **Read this section first when resuming in a new session.**

### Active branch / PR

- Branch: `private/shaib/restart`
- PR #1: [Phase 1 - Scanner and state database](https://github.com/shaib-art/offsite/pull/1)

### Phase 1 — Scanner and state database

**Goal:** CLI-accessible scan pipeline that records file metadata into SQLite. No integrity
checking, no copy/restore operations yet.

#### Completed iterations

| # | Scope | Key commits |
|---|-------|-------------|
| 1 | CLI `init-home` + SQLite schema bootstrap | early history |
| 2 | Recursive filesystem traversal (`scanner.py`) | `01b09f4` (red) `fe34f5d` (green) |
| 3 | Include/exclude folder filtering + scan counters | `3f2aaec` (red) `bfc57dc` (green) |
| 4 | Snapshot run lifecycle (`running → ok/failed`, rollback-safe) | `926f138` (red) `02704a9` (green) |
| 5 | `scan` CLI subcommand wiring `execute_snapshot_run` | `5de137d` (red) `87a3468` (green) |
| 6 | Quality gates and lint/type infrastructure (`tox` + CI workflows) | `phase 6 complete (local)` |

#### Between-iteration housekeeping applied

- SQLite `ResourceWarning` fix — `closing()` + `open_sqlite` pytest fixture (`3ff810a`)
- `pathlib`-first API policy + Windows long-path support (`18a2227`)
- Full codebase docstring pass (`4ad0942`, `1fa7453`)
- Monty Python test data style enforced in tests and `AGENTS.md` (`5b51b99`)
- Nested include exception under excluded base folder (`c139bfd`)

#### Current test / coverage status

- **33 tests passing**, 0 failures
- **93% overall coverage**
- Per-module: `cli.py` 97%, `scanner.py` 92%, `filtering.py` 91%,
  `snapshot.py` 97%, `db.py` 100%, `repository.py` 100%, `pathing.py` 83%
  (Windows-only `winreg` block uncoverable on macOS/Linux)

#### Recorded decisions (for phase final report)

- CLI framework: keep `argparse` for Phase 1; defer `click` migration.
- Rationale: current CLI scope is small, runtime dependencies are intentionally
  minimal in Phase 1, and migration now would add churn/risk to a stable green
  PR.
- Re-evaluation trigger (Phase 2+): consider `click` when CLI reaches ~5+
  subcommands, needs nested command groups/richer interactive UX, or
  `argparse` boilerplate duplication becomes material.
- Quality tooling verdict: use a combo approach.
  - Local/dev orchestration via `tox` for `flake8` (+ plugins), `pylint`,
    `mypy`, Markdown lint, and YAML lint.
  - CI meta validation via `super-linter` for Markdown, GitHub Actions,
    YAML, and JSON file formats.

#### Pending / next steps

- Phase 1 closure checklist:
  - [ ] All critical/high design-feedback findings resolved or deferred with rationale
  - [ ] CI matrix green on both `ubuntu-latest` and `windows-latest`
  - [ ] `pathing.py` lines 54-60 marked `# pragma: no cover` or covered via Windows CI job
  - [ ] Final report includes the recorded CLI framework verdict (`argparse` now, `click` deferred) and re-evaluation triggers
- Phase 2 candidates (not yet scoped):
  - SHA-256 integrity checksums (`hash_sha256` column already reserved)
  - Drive registration / detection
  - Copy / verify / restore operations
