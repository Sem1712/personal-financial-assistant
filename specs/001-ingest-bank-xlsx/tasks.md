---

description: "Implementation tasks for on-demand bank XLSX ingestion"
---

# Tasks: On-Demand Bank XLSX Ingestion

**Input**: Design documents from `specs/001-ingest-bank-xlsx/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/cli.md](./contracts/cli.md)

**Tests**: Included because the project constitution requires focused unit and PostgreSQL integration tests for all application modules and changed behavior.

**Organization**: Tasks are grouped by user story so each increment can be implemented and validated independently where the story dependencies allow.

## Phase 1: Setup

**Purpose**: Add required dependencies and local development/runtime configuration.

- [X] T001 Add runtime and development dependencies for `python-calamine`, Pydantic, `pydantic-settings`, SQLAlchemy async/PostgreSQL, Alembic, pytest, pytest-asyncio, testcontainers PostgreSQL, and Pyright in `pyproject.toml` and update `uv.lock` using uv.
- [X] T002 [P] Add a local Docker Compose PostgreSQL service and placeholder-only `.env.example` in `compose.yaml` and `.env.example`; do not add real credentials or weaken the existing `.env` ignore rule.

---

## Phase 2: Foundational

**Purpose**: Provide shared configuration, persistence, migrations, and PostgreSQL test support required by every story.

**⚠️ CRITICAL**: Complete this phase before user-story implementation.

- [X] T003 Implement Pydantic `Settings` and `.env` loading in `src/personal_financial_assistant/infrastructure/settings.py`, and test environment precedence, required secret URL validation, and redacted errors in `tests/unit/infrastructure/test_settings.py`; implement `Settings.database_url` and `IngestXlsxParameters.input_dir` exactly as defined in `specs/001-ingest-bank-xlsx/data-model.md`.
- [X] T004 Implement the shared async SQLAlchemy engine/session lifecycle, cleanup, and connection timeouts in `src/personal_financial_assistant/infrastructure/database.py`, using the settings from T003.
- [X] T005 Implement persistence entities and the initial Alembic schema in `src/personal_financial_assistant/infrastructure/models.py`, `alembic/env.py`, and `alembic/versions/0001_ingestion_schema.py`. Match these canonical fields in `specs/001-ingest-bank-xlsx/data-model.md`: SelectedAccount.id, SelectedAccount.account_reference, SelectedAccount.display_label; SourceFile.sha256, SourceFile.imported_at, SourceFile.transaction_row_count, SourceFile.account_id; Transaction Observation.source_file_sha256, Transaction Observation.sheet_index, Transaction Observation.row_number, Transaction Observation.account_id, Transaction Observation.transaction_date, Transaction Observation.amount_minor, Transaction Observation.currency, Transaction Observation.operation, Transaction Observation.details, Transaction Observation.booking_status, Transaction Observation.category, Transaction Observation.candidate_key, Transaction Observation.occurrence_ordinal; Transaction Occurrence.id, Transaction Occurrence.account_id, Transaction Occurrence.transaction_date, Transaction Occurrence.amount_minor, Transaction Occurrence.currency, Transaction Occurrence.booking_status, Transaction Occurrence.observation_ids, Transaction Occurrence.reconciliation_state. Do not make the four-field candidate key unique.
- [X] T006 [P] Add reusable real-PostgreSQL testcontainers setup in `tests/integration/conftest.py`; make database/container startup failures fail the integration tests rather than skip them.
- [X] T007 Verify the initial Alembic migration upgrades both an empty PostgreSQL database and a representative supported schema in `tests/integration/test_migrations.py`.

**Checkpoint**: Shared configuration, database session, schema, and PostgreSQL test fixture are ready.

---

## Phase 3: User Story 1 - Import the available bank exports (Priority: P1) 🎯 MVP

**Goal**: Import all eligible workbooks for the selected account into local persistent observations and current transactions.

**Independent Test**: From an empty PostgreSQL database, import synthetic supported XLSX exports and compare persisted transaction data, booking state, and categories with the expected rows.

### Tests for User Story 1

- [X] T008 [P] [US1] Create a stdlib-generated synthetic Intesa XLSX fixture builder in `tests/fixtures/intesa_xlsx.py`, covering variable preamble/header rows, all supported columns, blank/footer rows, and multiple transaction occurrences without using real account data.
- [X] T009 [US1] Add parser unit tests in `tests/unit/ingestion/test_xlsx_reader.py` for heading normalization/discovery, valid rows, exact EUR-cent conversion, date handling, blank/footer rows, invalid required fields, unsupported currencies, and unsupported workbook structures using T008.

### Implementation for User Story 1

- [X] T010 [P] [US1] Implement Pydantic CLI parameters and `ingest-xlsx --input-dir` argument validation in `src/personal_financial_assistant/cli.py`, citing `specs/001-ingest-bank-xlsx/data-model.md: IngestXlsxParameters.input_dir`; test missing, malformed, and relative paths in `tests/unit/cli/test_parameters.py`.
- [X] T011 [US1] Implement safe, non-recursive XLSX discovery and workbook normalization in `src/personal_financial_assistant/ingestion/xlsx_reader.py`; offload blocking reads/parsing, reject symlinks/temporary files/unsupported workbook parts, enforce documented workbook safety limits, and pass T009.
- [X] T012 [US1] Implement the initial import orchestration in `src/personal_financial_assistant/ingestion/service.py` to discover one account, parse and validate every eligible file before persistence, and atomically persist valid observations and occurrences through the shared async database session from T004.
- [X] T013 [US1] Wire the new command through the existing console entry point in `src/personal_financial_assistant/__init__.py` and add a real-PostgreSQL initial-import integration test in `tests/integration/test_ingestion_initial.py` for multiple files, all eligible dates, exact values, status, and category provenance.

**Checkpoint**: One on-demand invocation imports a valid folder into an empty database without external data flow.

---

## Phase 4: User Story 2 - Repeat imports and refresh booking state (Priority: P1)

**Goal**: Make imports idempotent while preserving co-occurring identical transactions and conservatively handling pending-to-booked changes.

**Independent Test**: Re-import identical, renamed, overlapping, reordered, and status-changed synthetic exports; verify occurrence counts, status, and unresolved observations.

### Tests for User Story 2

- [X] T014 [P] [US2] Add unit tests for file-digest idempotency, per-file candidate-key multiplicity, max-multiplicity merging, same-key duplicate preservation, order independence, and ambiguous pending matches in `tests/unit/ingestion/test_identity.py`.
- [X] T015 [US2] Add integration tests for repeated imports, renamed identical files, overlapping exports, pending-to-booked transitions, changed-key pending rows, and unresolved ambiguity in `tests/integration/test_ingestion_reconciliation.py`.

### Implementation for User Story 2

- [X] T016 [US2] Implement SHA-256 source-file deduplication, four-field candidate grouping, per-file occurrence counts, and deterministic max-multiplicity reconciliation in `src/personal_financial_assistant/ingestion/identity.py`; preserve multiple occurrences per candidate group and expose uncertain associations instead of merging them.
- [X] T017 [US2] Integrate the identity/reconciliation rules into `src/personal_financial_assistant/ingestion/service.py`; make exact byte-identical file digests no-ops, prevent booked-to-pending regressions, keep ambiguous pending records pending, retain unresolved booked observations, and never delete transactions due to export omission.

**Checkpoint**: Repeated and overlapping imports are idempotent under the documented heuristic, and ambiguity is visible rather than silently guessed.

---

## Phase 5: User Story 3 - Understand results and failures (Priority: P2)

**Goal**: Give the invoking user clear, sanitized outcomes and ensure failed batches do not partially update records.

**Independent Test**: Exercise empty input, malformed and changing files, invalid configuration, unavailable PostgreSQL, and interrupted batch persistence; verify exit outcomes, privacy, and transaction rollback.

### Tests for User Story 3

- [X] T018 [P] [US3] Add CLI tests for successful counts, empty-folder no-op, nonzero validation/configuration failures, and output redaction in `tests/unit/cli/test_ingest_command.py`.
- [X] T019 [US3] Add integration tests proving mixed valid/invalid files and persistence failures roll back the whole batch and concurrent invocations do not create duplicates in `tests/integration/test_ingestion_failures.py`.

### Implementation for User Story 3

- [X] T020 [US3] Implement the in-memory ingestion result fields and safe error categories in `src/personal_financial_assistant/ingestion/service.py`, matching `specs/001-ingest-bank-xlsx/data-model.md: Ingestion Run / Result.files_seen, Ingestion Run / Result.files_processed, Ingestion Run / Result.files_unchanged, Ingestion Run / Result.rows_read, Ingestion Run / Result.transactions_added, Ingestion Run / Result.transactions_updated, Ingestion Run / Result.observations_unchanged, Ingestion Run / Result.unresolved_observations, and Ingestion Run / Result.errors`.
- [X] T021 [US3] Implement sanitized CLI summaries, file/row references, explicit nonzero failure results, and non-leaking Pydantic/database error handling in `src/personal_financial_assistant/cli.py`; print counts only and never raw paths or financial values.
- [X] T022 [US3] Ensure full-batch validation and database persistence are atomic and safe against input-file mutation/concurrent invocations in `src/personal_financial_assistant/ingestion/service.py` and `src/personal_financial_assistant/infrastructure/database.py`; keep all blocking file work off the event loop.

**Checkpoint**: The user can distinguish success, no input, unresolved reconciliation, and failure without exposing financial data.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Complete documentation and quality validation across all stories.

- [X] T023 [P] Update `README.md` with the on-demand XLSX CLI workflow, `.env` configuration, local PostgreSQL prerequisites, and safe handling of downloaded bank files.
- [X] T024 [P] Review `specs/001-ingest-bank-xlsx/quickstart.md` against the implemented command and add only verified local setup, test, migration, and expected-output instructions.
- [X] T025 Run Ruff and strict Pyright against `pyproject.toml`, all unit tests, PostgreSQL/testcontainers integration and migration tests, and every validation scenario in `specs/001-ingest-bank-xlsx/quickstart.md`; record unavailable required services as blocked, not passed.

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependency; T001 and T002 may run in parallel.
- **Foundational (Phase 2)**: Begins after dependencies; T003 and T006 can proceed independently, T004 depends on T003, T005 depends on T004, and T007 depends on T005 and T006. This phase blocks all stories.
- **User Story 1 (Phase 3)**: Depends on the foundation. T008 and T010 can run in parallel; T009 depends on T008; T011 depends on T009; T012 depends on T004, T005, T010, and T011; T013 depends on T012.
- **User Story 2 (Phase 4)**: Depends on User Story 1's parser and persistence. T014 can proceed after the foundation; T015 depends on T012 and T014 and defines the integration behavior; T016 depends on T014; T017 depends on T015 and T016.
- **User Story 3 (Phase 5)**: Extends the completed CLI and importer; depends on User Stories 1 and 2. T018 can be written after T010; T019 depends on the import and reconciliation service; T020/T021 implement reporting and failure behavior; T022 completes atomic/concurrency guarantees.
- **Polish (Phase 6)**: Depends on all desired stories. T023 and T024 can run in parallel; T025 follows implementation and documentation.

### User Story Dependencies

- **User Story 1 (P1)**: Starts after the foundational phase; no dependency on another user story.
- **User Story 2 (P1)**: Depends on User Story 1 because it extends the importer with repeat-import and reconciliation behavior.
- **User Story 3 (P2)**: Depends on User Stories 1 and 2 because its result counts, error reporting, and rollback behavior cover the complete import workflow.

### Parallel Opportunities

- T001 and T002 are independent setup work.
- T003 and T006 can proceed in parallel after dependencies are available; T004/T005/T007 remain ordered by shared schema dependencies.
- Within User Story 1, T008 and T010 touch separate fixture/CLI files; parser tests follow the fixture builder.
- T014 is a separate identity test module and can start while User Story 1 is complete; it must finish before identity implementation T016.
- T018's CLI output tests can be prepared independently of the integration rollback tests.
- T023 and T024 update distinct documentation files.

## Parallel Example: User Story 1

```text
Task: T008 — Build synthetic XLSX fixtures in tests/fixtures/intesa_xlsx.py
Task: T010 — Add Pydantic CLI parameters in src/personal_financial_assistant/cli.py

Then:
Task: T009 — Add parser tests using the fixture builder
Task: T011 — Implement the XLSX reader against those tests
```

## Implementation Strategy

### MVP First (User Story 1)

1. Complete dependency setup and the shared settings/database/migration foundation.
2. Implement synthetic XLSX fixtures and parser tests.
3. Implement one-folder, one-account on-demand import with atomic persistence.
4. Validate User Story 1 independently using synthetic workbooks and real PostgreSQL.
5. Continue to User Story 2 before treating repeated imports as safe for regular use.

### Incremental Delivery

1. Deliver User Story 1 for an initial local import.
2. Deliver User Story 2 before repeated imports, covering deduplication and pending reconciliation.
3. Deliver User Story 3 for sanitized counts, explicit failures, and all-or-nothing behavior.
4. Complete cross-cutting docs and the configured quality gates.

## Notes

- Every task uses the required checkbox, sequential ID, optional `[P]`, applicable story label, action, and concrete file path.
- Tests are required by the project constitution and are grouped with the behavior they validate.
- No benchmark or elapsed-time task is included.
- Candidate keys are not unique IDs; follow the limitation documented in `research.md` and `data-model.md`.
- Do not commit the user's bank workbook, raw financial fixtures, or real `.env` credentials.
- T025 was verified with the complete repository quality gates and an isolated Compose
  project using an ephemeral loopback port, without disturbing the existing port 5432 service.

## Phase 7: Convergence

- [X] T026 CRITICAL Preserve observed booked and pending facts without fabricating pending status or arbitrary confirmed links when candidate multiplicity grows in `src/personal_financial_assistant/ingestion/identity.py` and `src/personal_financial_assistant/ingestion/service.py`; cover previously booked and pending groups, reordered rows, and ambiguous associations in `tests/unit/ingestion/test_identity.py` and `tests/integration/test_ingestion_reconciliation.py` per Constitution V, FR-011, FR-013, FR-014, FR-021, and SC-001 (contradicts).
- [X] T027 CRITICAL Distinguish genuinely recognizable footer text from incomplete transaction rows in `src/personal_financial_assistant/ingestion/xlsx_reader.py`, rejecting ambiguous single-field transaction rows instead of silently skipping them; test malformed and legitimate footer cases in `tests/unit/ingestion/test_xlsx_reader.py` per Constitution V, FR-004, and FR-020 (contradicts).
- [X] T028 CRITICAL Translate asyncpg connection and authentication failures into explicit sanitized CLI errors in `src/personal_financial_assistant/cli.py` or `src/personal_financial_assistant/infrastructure/database.py`; test actual driver exception types and redaction in `tests/unit/cli/test_ingest_command.py` and `tests/integration/test_ingestion_failures.py` per Constitution II, FR-017, and US3/AC3 (contradicts).
- [X] T029 CRITICAL Verify Alembic upgrades with representative persisted account, source, observation, and occurrence data in `tests/integration/test_migrations.py`, including an applicable existing supported schema and an empty database; document how the initial revision's lack of a prior ingestion schema is handled per Constitution IV and T007 (partial).
- [X] T030 Reject formulas in required transaction cells even when Calamine omits a formula-only row without a cached value in `src/personal_financial_assistant/ingestion/xlsx_reader.py`; add a synthetic regression in `tests/unit/ingestion/test_xlsx_reader.py` per plan: workbook safety and T011 (partial).
- [X] T031 Preserve accurate processing and digest-idempotency reporting for valid empty-table XLSX files, including repeated and mixed empty/nonempty batches, in `src/personal_financial_assistant/ingestion/service.py` and its unit and PostgreSQL integration tests per FR-016, SC-002, and T016 (partial).
- [X] T032 Complete the outstanding release checks in `specs/001-ingest-bank-xlsx/quickstart.md`: resolve the configured repository-wide Ruff formatting failure without masking it, safely verify the Compose startup and migration workflow without disturbing existing services, and rerun all required uv quality gates per Constitution development quality gates and T025 (partial).

## Phase 8: Convergence

- [X] T033 CRITICAL Preserve nonempty operation, details, and category values or explicitly reject unsupported cell types instead of silently treating them as absent in `src/personal_financial_assistant/ingestion/xlsx_reader.py`; cover numeric and other nontext values with focused parser and persistence tests per Constitution II and V, FR-005, and FR-020 (contradicts).
- [X] T034 CRITICAL Validate identifiable account information in supported workbook preambles against transaction rows and the selected account, including empty and mixed batches, without inventing account details when unavailable; ensure mismatches fail atomically with sanitized errors and add synthetic parser and PostgreSQL integration tests per Constitution V, FR-007, FR-015, and SC-004 (contradicts).
- [X] T035 CRITICAL Reject ambiguous note-shaped rows inside the transaction table rather than silently skipping them as footers; preserve supported trailing explanatory and blank footers and test note-shaped rows before later transactions in `src/personal_financial_assistant/ingestion/xlsx_reader.py` and `tests/unit/ingestion/test_xlsx_reader.py` per Constitution V, FR-004, FR-020, and T027 (contradicts).
