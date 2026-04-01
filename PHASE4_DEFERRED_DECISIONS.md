# Phase 4 Deferred Inputs Resolution

## Decision Summary

Both deferred inputs were evaluated during Phase 4 and are explicitly re-deferred to Phase 5 hardening due environment dependency and risk/effort profile.

## FB-20260321-006

- Item: rename heuristics inode/device support with migration safety.
- Phase 4 Decision: re-defer to Phase 5.
- Rationale:
  - Existing Phase 4 scope prioritized replay-safe recovery, checkpoint persistence, schema migration, and diagnostics.
  - Inode/device-aware rename heuristics require careful cross-platform behavior validation and migration safety testing against persisted placement state.
- Required Phase 5 Follow-up:
  - Add migration tests covering historical placement_index transitions.
  - Add Linux/macOS/Windows behavior matrix tests for inode/device edge cases.

## FB-20260321-007

- Item: real NAS performance baseline and runtime envelope capture.
- Phase 4 Decision: re-defer to Phase 5.
- Rationale:
  - Repository CI and unit/integration tests are simulation-first and do not provide stable physical NAS signal.
  - Benchmark quality requires controlled hardware/network setup and repeated measurements.
- Required Phase 5 Follow-up:
  - Run on real NAS path with fixed hardware and network profile.
  - Capture runtime envelope metrics and persist benchmark notes for operator expectations.
