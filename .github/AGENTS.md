# AGENTS.md (Template for Implementation Repository)

## Purpose

This repository implements the offsite backup application from planning artifacts.
All coding agents must follow the constraints below.

## Product Context

- Architecture/design source docs live in the planning repository.
- Implementation must stay aligned with architecture/specs and feedback governance.
- No silent divergence between implementation and approved design.

## Engineering Standards

- Prefer KISS over cleverness.
- Apply Single Responsibility at module/class/function level.
- Keep flow easy to read and test.
- Minimize block nesting using guard clauses and decomposition.
- Avoid code smells (duplication, long methods, hidden side effects, brittle conditionals).
- Use design patterns only when they clearly reduce complexity or improve maintainability.
- Keep code clean and pragmatic; avoid over-engineering.
- As iterations progress, scan for emerging duplication and record low-risk cleanup candidates for subsequent refactor commits.
- Prefer `pathlib.Path`-first APIs and internals; avoid `str`/`str | Path` path signatures unless unavoidable by third-party interfaces.
- Account for Windows long-path constraints: support extended-length path handling and warn when long-path policy (`LongPathsEnabled`) appears disabled.

## TDD Workflow (Mandatory)

For each requirement slice:
1. Write tests first (initially failing).
2. Implement minimal code to pass tests.
3. Refactor while keeping tests green.

Do not skip the failing-test step.

## Test and Coverage Gates

- Unit tests are mandatory for all behavior changes.
- Coverage target: >= 85% overall.
- Critical modules target: >= 90% (scan, plan, apply, integrity).
- Unit tests must not require physical NAS/HDD/cloud.
- Use mocks/simulations/fakes for environment dependencies.

## CI Requirements (GitHub Actions)

All branches/PRs must pass:
- lint-and-types
- unit-tests
- simulation-tests
- coverage-gate

Minimum CI matrix:
- ubuntu-latest
- windows-latest

## Commit Journal Policy

Use small, reviewable commits per requirement slice:
1. test commit (failing tests)
2. implementation commit (minimal passing code)
3. refactor commit (optional)

When an iteration passes its acceptance criteria, agents should automatically create the corresponding commit(s) for that iteration without requiring an extra user prompt.

Commits created from between-iteration interactions (for example, review feedback, policy tweaks, or housekeeping outside the active iteration scope) must use a commit message prefix of `reivew`.

Commit messages should include phase and scope for traceability.

## Traceability Requirements

Every behavior change should map clearly:
- requirement slice -> tests -> implementation -> commit history

When relevant, include links/references in PR notes to:
- architecture/spec sections
- feedback items
- ADR decisions

## Design Feedback Loop (Required)

If implementation reveals issues, create feedback records with:
- severity and confidence
- evidence (tests/logs/benchmarks/repro)
- recommended action

Before phase closure:
- all critical/high findings must be resolved or explicitly deferred with rationale.

## Stop Conditions

Pause and request clarification if:
- requirements and tests conflict
- safety policy is ambiguous
- passing tests would violate architecture constraints

## Security and Safety

- Treat deletion logic and integrity checks as safety-critical.
- Never bypass checksum verification in normal flows.
- Never enable irreversible deletion without explicit safeguards and tests.

## Implementation Style

- Favor explicit names over short cryptic names.
- Keep functions short and cohesive.
- Keep side effects localized and obvious.
- Add comments only where intent is non-obvious.

## Agent Output Expectations (Per Iteration)

Report at iteration end:
- tests added/changed
- code added/changed
- coverage before/after
- CI result summary
- findings for feedback loop
- note of any design drift and resolution path
