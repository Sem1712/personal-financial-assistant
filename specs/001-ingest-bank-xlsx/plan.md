# Implementation Plan: On-Demand Bank XLSX Ingestion

**Branch**: `001-ingest-bank-xlsx` (feature identifier; current Git branch is `main`) | **Date**: 2026-11-22 | **Spec**: [spec.md](./spec.md)

**Input**: Approved manual-ingestion handoff and user instruction to import available XLSX files on demand from the CLI.

## Summary

Add a local CLI workflow that reads the supported Intesa XLSX export from a user-selected folder, validates every eligible file, and atomically updates persistent transaction observations and current transaction state. Use an account/date/signed-amount/currency candidate key, not a purported unique natural key; preserve per-file multiplicity and leave uncertain pending-to-booked associations pending and reported.

## Technical Context

**Language/Version**: Python 3.15 (repository requirement)

**Primary Dependencies**: `python-calamine` for XLSX reading; Pydantic for CLI parameter models and `pydantic-settings` for environment/`.env` loading; `SQLAlchemy` async APIs and `asyncpg` for PostgreSQL; Alembic for schema migrations; pytest, async pytest support, and testcontainers for validation. Versions must be locked through uv and confirmed in implementation.

**Storage**: Locally hosted PostgreSQL in Docker. No database or migrations currently exist.

**Testing**: pytest; deterministic unit tests with synthetic workbook fixtures, CLI parameter validation, and `.env`/environment precedence and error redaction; PostgreSQL integration tests with testcontainers; migration tests against empty and representative existing schemas. Ruff and strict Pyright remain required quality gates.

**Target Platform**: Local Linux CLI initially; no background process or remote financial-data service.

**Project Type**: Python CLI application.

**Constraints**: All runtime I/O is async. XLSX parsing and file reads are synchronous library work and must be offloaded from the event loop. Financial values are exact EUR cents; no floating-point monetary calculations. Validate all files before applying a single atomic database transaction. Do not send financial data externally or log raw rows, account values, or amounts. Cap XLSX compressed/uncompressed sizes and reject unsupported workbook parts. Preserve duplicate multiplicity within each observed file; candidate keys may collide and cannot prove real-world identity. A maximum-multiplicity comparison across overlapping exports is an explicit heuristic and may undercount transactions never co-observed in one export.

**Execution simplicity**: Keep sequential orchestration with awaited offloading for synchronous file/XLSX work and settings loading; no parallel parsing pipeline is required. Pydantic field validation should be pure; filesystem existence/access checks belong in offloaded I/O. The user elected to retain async-first execution, so no blocking-runtime exception is requested.

**Scale/Scope**: One user, one selected Intesa account, direct `.xlsx` files from one configured input directory, all dates present in supplied files. No provider access, CSV, other banks, scheduled ingestion, or UI.

## Constitution Check

### Gate before Phase 0

| Principle / constraint | Gate | Plan |
|---|---|---|
| Explicit module boundaries and shared resources | Pass | Keep the XLSX/domain ingestion workflow separate from shared database infrastructure and analytics. Inject shared async session/configuration resources; do not make ingestion own general database setup. |
| Maintainability and simplicity | Pass | Add only dependencies needed for XLSX, Pydantic CLI/settings validation, async PostgreSQL persistence, migrations, and required tests. Keep orchestration sequential, interfaces narrow, and failures explicit. |
| Async-first execution | Pass with implementation condition | Run database/file I/O in async call paths. Offload synchronous XLSX parsing and file reads with bounded worker usage; set explicit database connection timeouts and cleanup. |
| Unit/integration tests | Pass with implementation condition | Cover parser, validation, identity reconciliation, CLI outcomes, failure atomicity, PostgreSQL persistence, and Alembic migrations using pytest and testcontainers. |
| Exact and explainable financial handling | Pass | Use integer minor units or exact Decimal conversion, explicit EUR, source observations, and documented identity limitations. Never interpret a heuristic association as a confirmed bank identifier. |
| Local PostgreSQL and migrations | Pass with implementation condition | Use Docker-hosted PostgreSQL, SQLAlchemy async APIs, and Alembic-reviewed schema changes; no runtime table creation. |
| Local bank data; no sensitive logs | Pass | Parse locally; store only in local PostgreSQL; sanitize CLI output. No provider or remote API calls. |

**Gate result**: No unjustified constitutional violation identified. The post-design gate remains conditional on meeting the implementation conditions above. No exception is requested.

## Project Structure

### Documentation (this feature)

```text
specs/001-ingest-bank-xlsx/
├── plan.md
├── research.md
├── data-model.md
├── contracts/
│   └── cli.md
├── quickstart.md
└── tasks.md             # created by /speckit-tasks
```

### Source Code (repository root)

```text
src/personal_financial_assistant/
├── __init__.py           # existing console entry point; dispatch CLI
├── cli.py                # Pydantic parameter model and sanitized reporting
├── ingestion/
│   ├── xlsx_reader.py    # workbook validation and normalized observations
│   ├── identity.py       # candidate groups and conservative reconciliation
│   └── service.py        # orchestration and batch result
└── infrastructure/
    ├── settings.py      # pydantic-settings and redacted config validation
    ├── models.py        # SQLAlchemy persistence entities
    └── database.py      # shared async engine/session ownership

alembic/
├── env.py
└── versions/

tests/
├── unit/
│   ├── ingestion/
│   └── cli/
└── integration/
    ├── test_ingestion_postgres.py
    └── test_migrations.py
```

**Structure Decision**: Extend the existing single Python project. Keep ingestion domain behavior under its own package and provide PostgreSQL sessions through focused shared infrastructure. Keep migrations outside runtime application modules. No frontend or separate project is justified.

## Phase 0: Research

Research decisions and sources are recorded in [research.md](./research.md). The principal trade-off is that account/date/signed amount/currency identifies a candidate group, not a transaction. Identical occurrences are counted as a multiset per workbook; across workbook snapshots, use the maximum observed multiplicity rather than summing. This is deterministic and idempotent for overlapping exports but can undercount separate identical transactions that never coexist in one file. Preserve source observations and report ambiguous status changes instead of guessing.

## Phase 1: Design

- [Data model](./data-model.md): account scope, export provenance, observations, candidate groups, occurrences, validation, and status reconciliation.
- [CLI contract](./contracts/cli.md): one on-demand local command and its sanitized results/errors.
- [Quickstart](./quickstart.md): local prerequisites and validation scenarios.

### Constitution Check (post-design)

| Principle / constraint | Result |
|---|---|
| Module boundaries and shared resources | Pass: parser/service/identity code is separate from the shared async PostgreSQL session boundary. |
| Async-first execution | Pass: blocking file and Calamine work is isolated in bounded worker threads; database access remains async. |
| Exact money and duplicate prevention | Pass with known limitation: exact minor units and multiset reconciliation prevent re-import inflation; no stable source ID means the documented key heuristic cannot resolve every identical occurrence. Ambiguous pending matches remain pending and are reported. |
| Local data and privacy | Pass: local workbook parsing and local PostgreSQL only; no provider/network ingestion; output excludes raw financial values. |
| Migrations and tests | Pass with implementation condition: Alembic migrations and real PostgreSQL testcontainers are required before feature completion. |

**Post-design gate result**: Pass with the explicit identity limitation documented in the spec and research. No constitution exception is needed.

### CLI and Configuration Boundary

- Parse command-line tokens with the standard CLI parser, then validate them with a Pydantic `IngestXlsxParameters` model. Use a required `Path` for `input_dir`; do not perform blocking existence checks in model validators.
- Define shared `Settings` with `pydantic-settings.BaseSettings`, loading `.env` from the invocation's working directory with UTF-8 encoding and `PFA_`-prefixed environment variables. Do not search parent directories. Process environment overrides `.env`; no command-line override of database secrets is exposed.
- Require `PFA_DATABASE_URL` for storage-backed ingestion; validate the async PostgreSQL URL scheme. Keep the value in a secret field and never print it or raw Pydantic validation exceptions. The missing-file case is acceptable only if required settings are provided by the environment.
- Load settings through an awaited offload because `.env` reading is synchronous. Keep environment loading in focused shared infrastructure rather than duplicating it in the CLI and database module.
- Read `.env` without modifying it; keep it out of version control. Any future example file must contain placeholders only.

## Complexity Tracking

No constitution violations or exceptions.
