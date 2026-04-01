# Offsite Backup v1 Phase 4 Execution Checklist

**Status:** COMPLETE (Phase 4 scope + local quality gates)
**Date:** 2026-04-01
**Branch:** private/shaib/phase4-replay-safe-recovery

---

## Purpose

Practical implementation and validation checklist for Phase 4:

- replay-safe recovery to home/NAS target
- checkpoint persistence across restarts
- schema versioning and migration handling
- richer operator diagnostics

This checklist assumes Phase 3 is closed and apply-result synchronization is stable.

---

## Phase 4 Exit Criteria

Phase 4 is complete only when all are true:

- [x] Recovery can rebuild the latest known good state from offsite media.
- [x] Recovery resume after interruption is safe and deterministic.
- [x] Checkpoint state survives process restart without corrupting workflow continuity.
- [x] Apply-result schema evolution path is implemented and tested.
- [x] Operator-visible failure diagnostics are structured and actionable.
- [x] Deferred inode/device and NAS benchmark items are explicitly resolved or re-deferred.
- [x] CI and coverage gates pass (>=85% overall, >=90% critical modules).

---

## Workstream Checklist

### A) Recovery Contract and Executor

- [x] Define restore input contract from placement index and synced inventory.
- [x] Validate target path safety before writes.
- [x] Restore files with deterministic ordering.
- [x] Verify integrity during restore.
- [x] Produce immutable recovery result/report artifact.

### B) Checkpoint Persistence

- [x] Persist checkpoint state for interrupted recovery.
- [x] Validate checkpoint/run identity on resume.
- [x] Reject conflicting or stale checkpoint state.
- [x] Reuse checkpoint model for upload/apply where it improves safety.

### C) Schema Versioning

- [x] Define envelope schema version transition rules.
- [x] Implement migration identifier validation.
- [x] Add supported migration handlers.
- [x] Reject unsupported or ambiguous schema transitions.

### D) Diagnostics and Operability

- [x] Expand `failures` taxonomy for operator guidance.
- [x] Distinguish integrity, checkpoint, schema, and media errors.
- [x] Keep diagnostics deterministic and safe for immutable reports.
- [x] Document operator response guidance in runbook/report notes.

### E) Deferred Inputs

- [x] FB-20260321-006 evaluated and explicitly re-deferred with migration-test follow-up requirement.
- [x] FB-20260321-007 evaluated and explicitly re-deferred pending real NAS benchmark environment.

---

## Tests Required

### Unit tests

- [x] Recovery contract validator.
- [x] Checkpoint persistence read/write and conflict detection.
- [x] Schema migration acceptance/rejection paths.
- [x] Diagnostics taxonomy rendering/serialization.

### Integration tests

- [x] Placement index -> recover happy path.
- [x] Interrupted recovery then resume.
- [x] Integrity mismatch during restore.
- [x] Unsupported schema migration rejection.
- [x] Recovery report artifact generation.

### CI checks

- [x] Ubuntu and Windows test jobs pass.
- [x] Lint and type checks pass.
- [x] Coverage gate for critical modules passes.

---

## Operator Validation

- [x] Simulate missing required drive and verify actionable failure output.
- [x] Simulate stale/conflicting checkpoint and verify fail-closed behavior.
- [x] Simulate corrupted payload and verify integrity stop.
- [x] Simulate unsupported envelope version and verify migration rejection.

---

## Phase Gate Close Checklist

- [x] All required tests pass.
- [x] CI green with required gates.
- [x] No unresolved critical/high findings for Phase 4.
- [x] Feedback log entries added for major decisions.
- [x] Phase 4 final report prepared.
- [x] Handoff notes drafted for Phase 5 hardening work.
