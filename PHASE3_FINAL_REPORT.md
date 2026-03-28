# Phase 3 Final Report: Upload and Apply-Result Synchronization

**Status:** COMPLETE (Phase 3 core scope + review hardening)
**Date:** 2026-03-28
**Branch:** private/shaib/phase3

---

## Executive Summary

Phase 3 delivers the end-to-end synchronization pipeline on top of the Phase 2 plan contract:

- plan-driven upload execution with retry/resume semantics
- checksum verification for transported payloads
- immutable office apply-result envelope contract
- home-side apply-result ingest that updates inventory + placement index
- stale-ingest guardrail that blocks planning when baseline sync is out of date
- idempotent re-ingest behavior for the same apply run
- post-review hardening for upload path containment, checksum validation, atomic immutable writes, and migration identifier validation

Implementation remains local-first with zero additional runtime dependencies.

---

## Scope Closure

| Requirement | Status | Evidence |
|---|---|---|
| Upload pipeline consumes plan allocation and payload references | COMPLETE | `offsite.core.upload.executor.execute_upload` |
| Retry/resume behavior | COMPLETE | retry loop + destination checksum skip; `test/test_upload.py` |
| Checksum verification post-upload | COMPLETE | upload integrity checks + mismatch fail path |
| Immutable apply-result contract | COMPLETE | `offsite.core.apply_sync.contract` |
| Home ingest updates apply history | COMPLETE | `office_apply_result` envelope metadata persisted |
| Home ingest updates drive free-space state | COMPLETE | `drive_inventory` ingest -> `home_drive_inventory` |
| Home ingest updates placement index | COMPLETE | `placement_index` upsert logic |
| Plan blocked when ingest missing/stale | COMPLETE | stale guard in plan drive resolution + regression test |
| Idempotent re-ingest | COMPLETE | run-id/hash check in ingest + test |

---

## Changed Files

### Runtime

- `src/offsite/cli.py`
- `src/offsite/core/state/db.py`
- `src/offsite/core/state/repository.py`
- `src/offsite/core/integrity/__init__.py`
- `src/offsite/core/integrity/checksum.py`
- `src/offsite/core/upload/__init__.py`
- `src/offsite/core/upload/executor.py`
- `src/offsite/core/apply_sync/__init__.py`
- `src/offsite/core/apply_sync/contract.py`
- `src/offsite/core/apply_sync/ingest.py`

### Tests

- `test/test_upload.py`
- `test/test_apply_sync.py`
- `test/test_cli_plan.py`
- `test/test_state_bootstrap.py`

### CI

- `.github/workflows/quality.yml`

---

## Test and Coverage Results

### Full test suite

- `pytest -q`
- Result: **98 passed**, 0 failed

### Phase 3 critical coverage gate

- `pytest --cov=offsite.core.upload --cov=offsite.core.apply_sync --cov=offsite.core.integrity --cov-fail-under=90 -q test/test_upload.py test/test_apply_sync.py`
- Result: **91.81%** (gate >=90%)

### Overall coverage gate

- `pytest --cov=src/offsite --cov-fail-under=85 -q`
- Result: **90.51%** (gate >=85%)

---

## Data Contract Examples

### Upload Manifest (`manifest.json`)

```json
{
  "schema_version": 1,
  "run_id": "upload-1f2e3d4c5b6a7d8e",
  "source_plan_id": "41->42",
  "files": [
    {
      "drive_label": "Office-01",
      "path_rel": "flying_circus/parrot.txt",
      "size_bytes": 500,
      "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    }
  ],
  "integrity": {
    "verified_files": 1,
    "mismatch_count": 0
  }
}
```

### Immutable Apply-Result Envelope

```json
{
  "schema_version": 1,
  "apply_run_id": "apply-coconut-001",
  "source_plan_id": "41->42",
  "uploaded_run_id": "upload-1f2e3d4c5b6a7d8e",
  "applied_snapshot_id": 42,
  "completed_at": "2026-03-28T10:00:00+00:00",
  "drive_inventory": [
    {
      "drive_label": "Office-01",
      "capacity_bytes": 500000000000,
      "free_bytes": 123456789000
    }
  ],
  "bytes_written": [
    {
      "drive_label": "Office-01",
      "bytes": 500
    }
  ],
  "bytes_deleted": [
    {
      "drive_label": "Office-01",
      "bytes": 25
    }
  ],
  "file_mappings": [
    {
      "path_rel": "flying_circus/parrot.txt",
      "drive_label": "Office-01",
      "version_token": "v2",
      "content_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "size_bytes": 500
    }
  ],
  "failures": [],
  "integrity_summary": {
    "verified_files": 1,
    "mismatch_count": 0
  },
  "envelope_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
}
```

---

## Notes on Reliability and Idempotency

- Upload resume: existing destination payload is skipped when checksum already matches source.
- Upload retry: transient copy failure retries up to configured limit.
- Upload path safety: plan payload paths must remain relative and contained under the allowed source/transport roots.
- Re-ingest safety: same `apply_run_id` + same `envelope_sha256` returns `already_ingested` without duplicate state rows.
- Conflict detection: same `apply_run_id` + different envelope hash is rejected.
- Immutable write safety: apply-result envelopes use exclusive-create semantics to avoid overwrite races.

---

## Unresolved Risks

- Contract versioning lifecycle is currently schema-v1 only; no migration helper for envelope schema evolution yet.
- Planning stale-check currently compares by snapshot id baseline and assumes monotonic, source-consistent snapshot lineage.
- CLI integration tests for `upload` and `ingest-apply-result` commands can be expanded for stronger end-to-end command-surface confidence.
- Review-driven hardening is in place for migration identifiers and upload path traversal, but broader hostile-input fuzzing is still not covered.
- Existing repository-wide sqlite `ResourceWarning` noise appears in some legacy tests and should be cleaned in a follow-up housekeeping pass.

---

## Next Actions (Phase 4 Preparation)

1. Add restore/recovery contract and replay-safe restore executor.
2. Introduce apply/upload checkpoint persistence in DB for crash-consistent resume across process restarts.
3. Add envelope schema versioning + migration strategy.
4. Add richer office diagnostics taxonomy in `failures` for operator guidance.
5. Revisit deferred items:
   - FB-20260321-006 rename heuristics inode/device support with migration safety.
   - FB-20260321-007 real NAS performance baseline and runtime envelope collection.
