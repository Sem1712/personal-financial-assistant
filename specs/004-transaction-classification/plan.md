# Implementation Plan: Transaction Classification and Context

**Branch**: `main` (actual Git branch; feature selector `004-transaction-classification`) | **Date**: 2026-11-28 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from [spec.md](./spec.md)

## Summary

Extend occurrence-based transactions with independent classification dimensions, per-dimension provenance and confidence, and separate user/AI context without altering source observations. Provide a typed async in-process update boundary and read-only information in the existing transaction detail view. Preserve import/reconciliation behavior and protect updates with transactional row locking; no editing interface, classifier, rules engine or budget calculations are included.

## Technical Context

**Language/Version**: Python >=3.15; existing browser JavaScript and HTML/CSS.

**Primary Dependencies**: Existing FastAPI, Pydantic, SQLAlchemy async, asyncpg and Alembic; no new dependencies.

**Storage**: Local PostgreSQL in Docker; add an Alembic revision after `0004_ui_import_run`.

**Testing**: uv-managed pytest and pytest-asyncio; testcontainers PostgreSQL for integration/migrations; existing Playwright browser tests; Ruff and strict Pyright.

**Target Platform**: Local single-user host with loopback-only browser application.

**Project Type**: Local Python CLI and browser application.

**Performance Goals**: No new latency or throughput benchmark is specified; retain existing paginated list behavior. Enrichment writes have a five-second database lock timeout.

**Constraints**: Async runtime I/O; no external financial data; exact existing monetary representations; confidence has at most two decimal places and excess precision is rejected without rounding; original observations retained; no edit controls or classification list/filter changes; errors sanitized; confirmed rollback distinct from unknown commit outcome.

**Scale/Scope**: One local user; reference verification of at least 100 synthetic occurrences; three dimensions and up to three independent context fields per occurrence. No new multi-user or service-provider integration.

## Constitution Check

*GATE: Pass before research; re-evaluated after design below.*

| Principle | Design and verification |
|-----------|-------------------------|
| I. Boundaries | Transactions owns typed enrichment behavior and read contracts; shared infrastructure owns models and database access; ingestion keeps identity/reconciliation responsibilities; UI consumes the public transactions boundary. No classifier is added. |
| II. Simplicity | Reuse existing service, detail route and rendering; add only enrichment tables and a focused typed operation. Errors, public contracts and affected README are documented. |
| III. Async-first | SQLAlchemy async sessions and explicit transactions; bounded lock wait, rollback/cancellation and engine ownership. No blocking runtime I/O or external model calls. |
| IV. Tests | Focused unit tests; real PostgreSQL integration tests for constraints, updates, concurrency and imports; migration tests against empty and representative prior schema; route/browser validation with synthetic data. Missing Docker/browser prerequisites are reported, not passed. |
| V. Financial reliability | Source observations remain separate and unmodified; no monetary calculation changes; unclassified and missing confidence stay explicit; sources identify interpretation, and no inferred financial judgment is introduced. |
| Technology/data | uv, Ruff, strict Pyright, async SQLAlchemy, Alembic and local PostgreSQL remain authoritative. No provider change, external transmission or sensitive logging. |
| Workflow | Spec provides acceptance and failure behavior; this plan identifies ownership, migration, contracts and verification. Full configured uv gates apply before merge. |

**Post-design gate**: PASS, subject to execution of the specified migration, integration, browser and quality checks. No constitutional exceptions are proposed. A commit-acknowledgment loss is reported as an unknown outcome rather than falsely asserting the rollback required for a confirmed failed update.

## Project Structure

### Documentation (this feature)

```text
specs/004-transaction-classification/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── transaction-enrichment.md
└── tasks.md             # generated later by /speckit-tasks
```

### Source Code (repository root)

```text
src/personal_financial_assistant/
├── infrastructure/models.py       # persistence mappings and constraints
├── transactions/                  # public typed enrichment and detail read
├── ingestion/                     # unchanged matching behavior; integration verification
└── ui/
    ├── transaction_routes.py      # existing detail response
    └── static/                    # read-only detail rendering
alembic/versions/                  # reviewed migration
tests/
├── unit/transactions/ and unit/ui/
├── integration/                   # real PostgreSQL, migration, ingestion and HTTP contracts
└── browser/                       # read-only detail behavior
```

**Structure Decision**: Extend existing modules rather than introducing a new independent subsystem. Enrichment data belongs to transaction occurrences; bank-source evidence remains owned by ingestion. Update [README.md](../../README.md) with the actual detail behavior and in-process public boundary when implemented.

## Phase 0: Research

Decisions and alternatives are recorded in [research.md](./research.md). In particular, ingestion's advisory lock is import-specific, so enrichment writers serialize on the occurrence row; automated replacements remain permitted as explicitly clarified. Source observations, list filters and occurrence identity are not repurposed.

## Phase 1: Design

1. Add dimension and context persistence with database constraints, restrictive occurrence references and a guarded downgrade. Existing and newly imported occurrences have no inferred classification.
2. Provide typed async partial updates through the transaction public interface. Validate all inputs, lock the occurrence, atomically modify only requested fields, and distinguish failed rollback from unknown commit outcome.
3. Extend the existing detail read with a coherent occurrence/observations/enrichment snapshot and additive response fields. Do not alter search output or bank-category filter behavior.
4. Present labeled classification and context only in transaction details, rendering untrusted text safely; keep existing accessibility, navigation, loading and retry behavior.
5. Test supported and invalid values, confidence bounds and excess-precision rejection, partial clearing and replacements, unknown/unresolved and duplicate-looking occurrences, retention over repeated import and booking reconciliation, isolation from source observations, concurrent writers, migration upgrade/downgrade and privacy. Verify the 100-occurrence reference set and the five-person task exercise specified in success criteria using a synthetic demo isolated from the application database.

Detailed schemas, state transitions and error behavior: [data-model.md](./data-model.md) and [contract](./contracts/transaction-enrichment.md). Runnable verification and prerequisites: [quickstart.md](./quickstart.md).

## Complexity Tracking

No constitutional violations or exceptions.
