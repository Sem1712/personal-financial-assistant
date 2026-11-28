# Implementation Plan: Merchant Identification and Classification Rules

**Branch**: `main` (actual Git branch; feature selector `005-merchant-classification-rules`) | **Date**: 2026-11-28 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from [spec.md](./spec.md)

## Summary

Add a local async rules boundary for merchant matching, category preferences, occurrence overrides and user review of AI suggestions. Evaluate newly created occurrences after the import commits, retaining durable per-occurrence evaluation work so a failure cannot undo bank data or disappear after interruption. Explicit reapplication handles existing occurrences. Preserve source evidence, existing enrichment semantics and the absence of user-facing rule controls.

## Technical Context

**Language/Version**: Python >=3.15, managed by uv.

**Primary Dependencies**: Existing SQLAlchemy async, asyncpg, Pydantic, Alembic and FastAPI; no new dependencies or model provider.

**Storage**: Local PostgreSQL in Docker. Add a reviewed Alembic revision after `0006_category_whitespace`; preserve legacy data and guard destructive downgrade.

**Testing**: uv-managed pytest and pytest-asyncio; testcontainers PostgreSQL for persistence, concurrency, import and migration contracts; Ruff and strict Pyright.

**Target Platform**: Local single-user host; existing CLI and loopback web application.

**Project Type**: Local Python CLI and browser application with typed in-process service boundaries.

**Performance Goals**: No latency target specified. Evaluate each occurrence in bounded transactions, sequentially by default; imports must not spawn unbounded tasks or wait on model calls.

**Constraints**: Async runtime I/O; no financial data or prompts sent externally; preserve source observations, transaction identity and non-category dimensions; no user-facing rule controls; distinguish confirmed rollback from unknown commit; report partial evaluation failure without rolling back committed imports.

**Scale/Scope**: One trusted local user and application consumers. Acceptance includes 100 synthetic descriptions, 20 protected-decision attempts and 50 selected/unselected occurrences; no unsubstantiated production volume target.

## Constitution Check

*Pre-research gate: PASS. Post-design gate: PASS, contingent on the verification below; no exceptions proposed.*

| Principle | Design and verification |
|-----------|-------------------------|
| I. Boundaries | A focused rules module owns matching, rule lifecycle, approvals and evaluation; ingestion owns import and writes only durable evaluation intents through shared infrastructure, then calls the public rules boundary after commit. Transactions owns category enrichment and occurrence locking. No private cross-module imports. |
| II. Simplicity | Reuse existing classification, import, validation and database conventions. Literal matching only. The durable work record is needed to prevent lost evaluation after an import commits. Public contracts, failures and README changes are documented. |
| III. Async-first | Async sessions and explicit transactions; sequential bounded evaluation, bounded lock waits, cancellation cleanup and caller-owned engine/connection. No runtime network calls or blocking I/O. |
| IV. Tests | Deterministic unit tests; real PostgreSQL integration tests for module contracts, import persistence, transactions, locks, recovery and migration from empty and representative prior schemas. Existing UI/CLI contracts are regression-tested; no live model dependency. |
| V. Financial reliability | Preserve source evidence and all non-category data; never infer amounts or confidence; surface provenance, ambiguity, conflict and failure. Overrides and confirmed rules are protected as specified. |
| Technology/data | uv, Ruff, strict Pyright, async SQLAlchemy, Alembic and Docker PostgreSQL remain in force. Financial data and rule information remain local and logs are sanitized. |
| Workflow | Spec defines inputs, outputs, failure and acceptance; this plan identifies ownership, async, schema and verification. Required full uv quality gates remain mandatory before merge. |

## Project Structure

### Documentation (this feature)

```text
specs/005-merchant-classification-rules/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── merchant-rules.md
└── tasks.md             # generated later by /speckit-tasks
```

### Source Code (repository root)

```text
src/personal_financial_assistant/
├── rules/                     # new public rule-management and evaluation boundary
├── ingestion/service.py       # enqueue new occurrence IDs and evaluate after import commit
├── transactions/              # shared occurrence/category update boundary
├── infrastructure/models.py   # shared persistence mappings and constraints
├── cli.py                      # import evaluation summary and explicit failures
└── ui/                         # additive import-result warnings; no rule controls
alembic/versions/               # reviewed schema migration after 0006
tests/
├── unit/rules/ and unit/ingestion/
└── integration/                # real PostgreSQL contracts, concurrency, imports, migrations
```

**Structure Decision**: Introduce one cohesive `rules` module because reusable merchant and preference lifecycle is distinct from transaction enrichment and bank ingestion. Store shared database records in infrastructure, not in another module's private implementation. Existing clients retain compatible import and transaction behavior; the import result adds sanitized evaluation reporting. Update [README.md](../../README.md) to describe automatic new-occurrence evaluation, retries, safeguards and service-only rule management.

## Phase 0: Research

Resolved decisions, trade-offs and relevant repository evidence are in [research.md](./research.md). There are no outstanding `NEEDS CLARIFICATION` items. In particular, preserve the current atomic import boundary and use durable work records for post-commit evaluation; treat explicit user approval as scoped to revisions and occurrence evidence.

## Phase 1: Design

1. Add merchant, matching-entry, preference/default, override, suggestion/review, approval and evaluation-work persistence with validated references, revisions and explicit states. Do not backfill classifications or import existing occurrences into the new evaluation queue.
2. Provide typed async public operations for trusted application consumers. Separate user-directed actions from AI/service proposals, preserving generation provenance through intermediate services and transformations; no new model calls, browser rule controls or rule-management HTTP routes.
3. Implement deterministic matching and category selection, including per-occurrence AI conflict blocking before precedence, kind-qualified rule references, explainable outcomes and no fabricated confidence. Retain the existing general enrichment update policy; explicit overrides are separate records and are protected during rule application.
4. Insert an evaluation-work record for every newly created occurrence in the same transaction as the import, including unresolved occurrences with no linked observation. After successful commit, process those records in bounded per-occurrence transactions. Existing linked occurrences, duplicate imports and booking reconciliation do not enqueue work. Imported observations and prior enrichments remain intact on evaluation failure.
5. Serialize rule changes, approvals and evaluations with a shared configuration lock followed by occurrence locking; recompute the full reviewed snapshot before approval so new applicable rules or changes to overrides, current category or evidence cannot change the approved result unnoticed. Invalidate scoped approvals when referenced rules or occurrence evidence change. Extend import linking to take the occurrence lock before changing its linked evidence, without changing reconciliation rules.
6. Expose sanitized import evaluation counts and per-occurrence statuses through the in-process contract, and non-sensitive warning summaries through existing CLI and import status behavior. Explicitly distinguish pending, failed and unknown outcomes; make work queryable and retryable after interruption.
7. Test literal normalization, precedence, ties, ambiguities, overrides, kind-qualified references, forwarded AI provenance, conflicts and stale approval previews; test 100/20/50/automatic-import success criteria including failed/pending outcomes, import crash/retry, unknown commit, concurrency, privacy, migrations and existing import/UI regressions. Use real PostgreSQL for all persistence and migration verification.

Detailed schemas, state transitions and concurrency: [data-model.md](./data-model.md). Public input/output and failure contracts: [merchant-rules.md](./contracts/merchant-rules.md). Validation commands and expected results: [quickstart.md](./quickstart.md).

## Complexity Tracking

No constitutional violations or exceptions.
