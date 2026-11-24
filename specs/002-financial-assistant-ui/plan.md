# Implementation Plan: Financial Assistant Interface

**Branch**: `main` (actual Git branch; `002-financial-assistant-ui` is the feature identifier) | **Date**: 2026-11-23 | **Spec**: [spec.md](./spec.md)

**Input**: [Clarified feature specification](./spec.md)

## Summary

Provide a local browser interface that opens on an unavailable chat placeholder and offers an on-demand folder import and an occurrence-based transaction explorer. Extend the existing Python application with a loopback-only async web boundary, a narrowly scoped transaction read service, and a durable, non-sensitive UI import-run record. Reuse existing ingestion and shared async database infrastructure; do not implement conversation or reporting.

## Technical Context

**Language/Version**: Python 3.15 or newer; browser-native HTML, CSS, and JavaScript.

**Primary Dependencies**: Existing async SQLAlchemy, asyncpg, Pydantic, Alembic and ingestion dependencies; add FastAPI and Uvicorn through uv for the local web boundary. Use same-origin static assets without a frontend package manager or external assets. Add HTTP and browser test dependencies through uv as needed, with versions verified and locked during implementation.

**Storage**: Existing locally hosted PostgreSQL. Read existing transaction and observation tables; add an Alembic-managed import-run table for recovery and sanitized outcomes. Do not persist export paths or financial payloads in the run record or browser storage.

**Testing**: pytest and pytest-asyncio for isolated async unit tests of every new application module, including the transaction service and workbook worker, and HTTP contract tests; testcontainers with real PostgreSQL for queries, ingestion integration, locking, recovery and migration tests; automated local browser journeys plus the specified usability study. Ruff, formatting, strict Pyright, and applicable pytest suites through uv.

**Target Platform**: Local single-user Linux host, with a modern browser on the same host; service bound only to `127.0.0.1`.

**Project Type**: Existing Python application with a local browser UI, not a remotely hosted service.

**Performance Goals**: Meet spec SC-001 through SC-006; page transaction results to bound work. No unapproved latency or throughput SLA is assumed.

**Constraints**: Async runtime I/O with bounded concurrency, explicit timeouts and lifecycle. UI workbook discovery, individual reads, and snapshot verification run in an owned local worker subprocess with 60-second per-operation deadlines and bounded termination; the CLI's existing path remains unchanged. Exact EUR cents, no binary floating point for money. No external financial-data transfer, external frontend assets, financial values in logs or query strings, or hidden import failures. Enforce local host/origin and request-token protections; local untrusted processes are not an authentication boundary. Source text is untrusted. Existing ingestion atomicity and advisory locking remain authoritative.

**Scale/Scope**: One user and one account, a single local UI process and at most one UI import at a time; historical occurrences are paged. Imports, transaction reading/filtering, and a disabled future-chat/report placeholder only.

## Constitution Check

### Gate before Phase 0

| Principle or constraint | Gate and design condition |
|---|---|
| Module boundaries and shared resources | Pass: web presentation, transaction reads, ingestion and shared infrastructure have separate documented interfaces; use shared async sessions and the public ingestion service. |
| Simplicity and explicit errors | Pass: one Python project, one small local UI, no speculative chat/report implementation; show sanitized failure and unknown outcomes explicitly. |
| Async-first | Conditional pass: async SQLAlchemy and HTTP; isolate UI workbook operations in an owned worker with explicit deadlines, termination, reaping and shutdown; own all tasks and DB connections. |
| Tests | Conditional pass: focused deterministic unit, HTTP/UI contract and real-PostgreSQL integration tests; test new migration against empty and existing schemas. |
| Financial correctness | Pass: signed integer cents, exact parsing, explicit EUR, source categories as suggestions, and unresolved state without invented matches. |
| PostgreSQL and migrations | Conditional pass: add a reviewed Alembic revision for durable run recovery; no runtime table creation. |
| Locality and privacy | Conditional pass: loopback-only UI, no third-party content or logs of sensitive data, and browser request protections described in [research.md](./research.md). |

No constitutional exception is requested. Conditions must be satisfied by implementation and verified before merge.

## Project Structure

### Documentation (this feature)

```text
specs/002-financial-assistant-ui/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── contracts/
│   └── local-ui.md
├── quickstart.md
└── tasks.md             # created by /speckit-tasks
```

### Source Code (repository root)

```text
src/personal_financial_assistant/
├── cli.py                    # retain ingest-xlsx; add serve-ui entry point
├── ingestion/                # existing import plus bounded UI workbook worker
├── transactions/             # new public occurrence/query read boundary
├── ui/                       # local web routes, import coordinator, static UI
└── infrastructure/           # shared async database, settings and persistence models
alembic/versions/             # reviewed import-run migration
tests/
├── unit/                     # query validation, coordinator, presentation and HTTP contract
├── integration/              # PostgreSQL reads, imports, lock/recovery and migrations
└── browser/                  # local end-to-end UI journeys
```

**Structure Decision**: Extend the existing package rather than introducing a separate frontend project. The transaction read module owns its query and response contract; UI code calls that boundary and the public ingestion service, not ingestion-private parsing or reconciliation. Shared infrastructure owns sessions and the import-run persistence schema. Extend the ingestion/session public boundary to accept a pinned async connection and a UI workbook worker while preserving its existing engine-based CLI interface; do not duplicate parsing or reconciliation logic. Existing CLI behavior remains supported.

## Phase 0: Research

Decisions, alternatives, and sources are documented in [research.md](./research.md). In particular, a durable run record is necessary to distinguish an interrupted or disconnected import from a confirmed success, and one long-lived PostgreSQL advisory lock prevents another UI process from misclassifying a live run as stale.

## Phase 1: Design

- [Data model](./data-model.md): occurrence projections, filter semantics, run lifecycle and migration requirements.
- [Local UI and HTTP contract](./contracts/local-ui.md): navigation, requests, errors, local trust boundary and background-job behavior.
- [Quickstart](./quickstart.md): prerequisites and runnable verification steps after implementation.

### Constitution Check (post-design)

| Principle or constraint | Result |
|---|---|
| Responsibilities and shared resources | Pass: UI calls explicit transaction and ingestion boundaries; DB ownership remains shared. |
| Async, resource and failure handling | Conditional pass: one owned task, pinned lock connection and file-operation subprocess, explicit deadlines and termination, fail-closed handling if cleanup cannot be confirmed, and safe recovery. |
| Exactness and explainability | Pass: cents and currency remain exact; linked source evidence is distinct from uncertain occurrences. |
| Privacy and local operation | Conditional pass: validated loopback/Host/Origin, per-process token, safe rendering and no-sensitive-output rules are tested. |
| Persistence and verification | Conditional pass: reviewed migration, empty/existing-schema testcontainers tests, focused UI/contract/unit tests and full configured gates remain mandatory. |

**Post-design gate**: Pass subject to the stated implementation and verification conditions; no exception requested.

## Complexity Tracking

No constitution violations or exceptions. The import-run table and singleton lock are justified by the specified unknown-outcome recovery and the need not to declare another live process's job interrupted.
