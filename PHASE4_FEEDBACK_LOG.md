# Phase 4 Feedback Log

## Major Decisions

1. Recovery executor remains deterministic by sorted `path_rel` order.
2. Recovery and upload now both support checkpoint-backed resume using shared `workflow_checkpoint` persistence.
3. Resume is fail-closed on conflicting run identity (`workflow_kind` + `checkpoint_key` + `run_id`).
4. Schema transition policy is explicit: schema-v1 current, schema-v0 accepted only via validated `migration_id` and supported handler.
5. Recovery diagnostics taxonomy standardized to `integrity`, `checkpoint`, `schema`, and `media`.
6. Recovery reports are immutable and include structured `failures` diagnostics for operator actionability.
7. Deferred inputs FB-20260321-006 and FB-20260321-007 explicitly re-deferred to Phase 5 with rationale and required follow-up validation.
