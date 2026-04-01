# Offsite Backup v1 Phase 4 Execution Checklist

**Status:** IN PROGRESS (kickoff)
**Date:** 2026-04-01
**Branch:** main

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

- [ ] Recovery can rebuild the latest known good state from offsite media.
- [ ] Recovery resume after interruption is safe and deterministic.
- [ ] Checkpoint state survives process restart without corrupting workflow continuity.
- [ ] Apply-result schema evolution path is implemented and tested.
- [ ] Operator-visible failure diagnostics are structured and actionable.
- [ ] Deferred inode/device and NAS benchmark items are explicitly resolved or re-deferred.
- [ ] CI and coverage gates pass (>=85% overall, >=90% critical modules).

---

## Workstream Checklist

### A) Recovery Contract and Executor

- [x] Define restore input contract from placement index and synced inventory.
- [x] Validate target path safety before writes.
- [ ] Restore files with deterministic ordering.
- [ ] Verify integrity during restore.
- [ ] Produce immutable recovery result/report artifact.

### B) Checkpoint Persistence

- [x] Persist checkpoint state for interrupted recovery.
- [x] Validate checkpoint/run identity on resume.
- [x] Reject conflicting or stale checkpoint state.
- [ ] Reuse checkpoint model for upload/apply where it improves safety.

### C) Schema Versioning

- [ ] Define envelope schema version transition rules.
- [ ] Implement migration identifier validation.
- [ ] Add supported migration handlers.
- [ ] Reject unsupported or ambiguous schema transitions.

### D) Diagnostics and Operability

- [ ] Expand `failures` taxonomy for operator guidance.
- [ ] Distinguish integrity, checkpoint, schema, and media errors.
- [ ] Keep diagnostics deterministic and safe for immutable reports.
- [ ] Document operator response guidance in runbook/report notes.

### E) Deferred Inputs

- [ ] FB-20260321-006 evaluated and decision captured with migration tests if adopted.
- [ ] FB-20260321-007 benchmark executed and runtime envelope captured.

---

## Tests Required

### Unit tests

- [x] Recovery contract validator.
- [x] Checkpoint persistence read/write and conflict detection.
- [ ] Schema migration acceptance/rejection paths.
- [ ] Diagnostics taxonomy rendering/serialization.

### Integration tests

- [ ] Placement index -> recover happy path.
- [ ] Interrupted recovery then resume.
- [ ] Integrity mismatch during restore.
- [ ] Unsupported schema migration rejection.
- [ ] Recovery report artifact generation.

### CI checks

- [ ] Ubuntu and Windows test jobs pass.
- [ ] Lint and type checks pass.
- [ ] Coverage gate for critical modules passes.

---

## Operator Validation

- [ ] Simulate missing required drive and verify actionable failure output.
- [ ] Simulate stale/conflicting checkpoint and verify fail-closed behavior.
- [ ] Simulate corrupted payload and verify integrity stop.
- [ ] Simulate unsupported envelope version and verify migration rejection.

---

## Phase Gate Close Checklist

- [ ] All required tests pass.
- [ ] CI green with required gates.
- [ ] No unresolved critical/high findings for Phase 4.
- [ ] Feedback log entries added for major decisions.
- [ ] Phase 4 final report prepared.
- [ ] Handoff notes drafted for Phase 5 hardening work.
