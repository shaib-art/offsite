# Phase 4 Operator Runbook Notes

This note maps recovery failure diagnostics to operator actions.

## Failure Taxonomy

Recovery immutable reports emit `failures` entries with:

- `category`
- `code`
- `message`
- optional `path_rel`

Supported categories:

- `integrity`
- `checkpoint`
- `schema`
- `media`

## Operator Actions

### media

- `missing_payload`: verify required offsite drive is connected and mounted; validate transport media path and uploaded run folder.
- `copy_failed`: treat as transient media read/write fault first; retry after reconnect/remount; replace failing cable/port/drive if repeated.
- `immutable_report_exists`: do not overwrite existing report; start a new restore run/report path.

### integrity

- `checksum_mismatch`: stop recovery; quarantine suspect payload; re-run upload integrity verification from source and re-transport clean payloads.
- `size_mismatch`: treat as corruption/truncation; do not continue until payload is re-staged and verified.

### checkpoint

- `conflicting_run_id`: stale/conflicting checkpoint state; fail closed; investigate checkpoint key ownership and start a clean run if required.
- `stale_checkpoint`: destination no longer matches persisted checkpoint progress; invalidate checkpoint and restart deterministic replay.

### schema

- `invalid_recovery_request`: request contract mismatch; fix envelope/request generation and rerun validation before execution.

## Safety Rules

- Recovery reports are immutable (exclusive-create write mode).
- Resume is deterministic and keyed by `(workflow_kind, checkpoint_key, run_id)`.
- Conflicting checkpoint identity is rejected; never force resume across run IDs.
