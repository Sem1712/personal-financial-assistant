---
description: "Implementation tasks for the financial assistant interface"
---

# Tasks: Financial Assistant Interface

**Input**: [spec.md](./spec.md), [plan.md](./plan.md), [research.md](./research.md), [data-model.md](./data-model.md), [local UI contract](./contracts/local-ui.md), and [quickstart.md](./quickstart.md).

**Tests**: Required by the constitution and the specification's acceptance criteria. Write focused tests before the corresponding implementation, and confirm they fail for the intended missing behavior. Database integration and migration tests use real PostgreSQL testcontainers; browser tests use synthetic data.

**Organization**: Tasks are grouped by user story. `[P]` marks tasks that can run concurrently once their stated prerequisites are complete and that do not edit the same files.

## Phase 1: Setup

**Purpose**: Establish dependencies and reusable test fixtures without changing existing CLI behavior.

- [X] T001 Add and lock Python 3.15-compatible FastAPI, Uvicorn, HTTP contract-test, and local browser-test dependencies through uv in `pyproject.toml` and `uv.lock`; verify local browser provisioning does not require external assets at runtime.
- [X] T002 [P] Add reusable synthetic UI/import and browser fixtures in `tests/fixtures/ui.py` and `tests/browser/conftest.py`, using the existing XLSX fixtures and avoiding real financial data.

## Phase 2: Foundational

**Purpose**: Establish a local-only, secure, async application shell shared by all stories.

- [X] T003 [P] Write HTTP boundary tests for loopback Host and port, Origin, token, Fetch Metadata, JSON content type, security headers, sanitized validation errors, and absent sensitive logs in `tests/unit/ui/test_security.py` against `specs/002-financial-assistant-ui/contracts/local-ui.md`.
- [X] T004 [P] Write CLI tests for the new loopback-only `serve-ui` command and unchanged `ingest-xlsx` behavior in `tests/unit/cli/test_serve_ui.py`.
- [X] T005 Implement exact Host/Origin checks, per-process bootstrap token, same-origin API protection, no-store/CSP/frame headers, and safe error/log handling in `src/personal_financial_assistant/ui/security.py` and `src/personal_financial_assistant/ui/errors.py`.
- [X] T006 Implement the async FastAPI application lifecycle, locally served packaged assets, route registration, shared configuration/engine ownership and explicit unavailable-storage behavior in `src/personal_financial_assistant/ui/app.py` and `src/personal_financial_assistant/ui/__init__.py`; do not create tables at runtime.
- [X] T007 [P] Build the accessible shared HTML/CSS and client request/navigation shell in `src/personal_financial_assistant/ui/static/index.html`, `src/personal_financial_assistant/ui/static/styles.css`, and `src/personal_financial_assistant/ui/static/app.js`, with the [request deadline](./data-model.md#workbook-deadlines-and-cleanup), all text safely rendered and no external assets.
- [X] T008 Add `serve-ui` at `127.0.0.1:8765` with access logs disabled in `src/personal_financial_assistant/cli.py`, preserving the existing CLI and its errors; ensure static assets are included in the installed package via `pyproject.toml`.
- [X] T009 Run the foundational security and CLI tests in `tests/unit/ui/test_security.py` and `tests/unit/cli/test_serve_ui.py`, and verify `src/personal_financial_assistant/ui/static/index.html` is available from the installed application.

**Checkpoint**: Secure local shell and existing CLI are independently verifiable. Story work can proceed after this foundation.

## Phase 3: User Story 1 - Start an import and understand its outcome (Priority: P1)

**Goal**: Start a folder import, show its result, prevent conflicting navigation/starts, and recover uncertain outcomes safely.

**Independent Test**: From the local UI, import valid, empty, repeated and invalid synthetic folders; compare displayed counts and errors with stored data, then exercise conflict and restart/unknown-outcome behavior.

### Tests for User Story 1

- [X] T010 [P] [US1] Write async unit tests for import validation, state transitions, scheduling, sanitization, cancellation, lost-lock, cleanup failure blocking new imports, and indeterminate terminal-state behavior in `tests/unit/ui/test_import_coordinator.py`, and subprocess deadlines, termination, reaping, credential isolation and cleanup failure in `tests/unit/ingestion/test_ui_worker.py`.
- [X] T011 [P] [US1] Write HTTP contract tests for `POST /api/imports` and `GET /api/imports/current`, including status codes, counts, no path disclosure, conflicts and unavailable storage even with an empty folder, in `tests/unit/ui/test_import_routes.py`.
- [X] T012 [P] [US1] Write real-PostgreSQL integration tests for valid, empty, repeated, malformed and competing imports, singleton ownership, recovery, commit ambiguity, connection loss, and timeouts during discovery, read and snapshot verification with confirmed rollback or unknown outcome in `tests/integration/test_ui_imports.py`.
- [X] T013 [P] [US1] Extend migration tests in `tests/integration/test_migrations.py` for upgrade from an empty database and the previous supported schema with representative transactions, retention of existing data, constraints, and downgrade behavior.
- [X] T014 [P] [US1] Write a synthetic browser test for folder entry, all import states/counts, navigation and duplicate-start blocking, refresh/reopen, timed-out requests without resubmission, and unknown outcomes in `tests/browser/test_import.py`.

### Implementation for User Story 1

- [X] T015 [P] [US1] Define the run persistence model in `src/personal_financial_assistant/infrastructure/models.py` using [UI import run.id](./data-model.md#ui-import-run-new-postgresql-entity), [UI import run.state](./data-model.md#ui-import-run-new-postgresql-entity), [UI import run.started_at](./data-model.md#ui-import-run-new-postgresql-entity), [UI import run.finished_at](./data-model.md#ui-import-run-new-postgresql-entity), [UI import run.files_seen](./data-model.md#ui-import-run-new-postgresql-entity), [UI import run.files_processed](./data-model.md#ui-import-run-new-postgresql-entity), [UI import run.files_unchanged](./data-model.md#ui-import-run-new-postgresql-entity), [UI import run.rows_read](./data-model.md#ui-import-run-new-postgresql-entity), [UI import run.transactions_added](./data-model.md#ui-import-run-new-postgresql-entity), [UI import run.transactions_updated](./data-model.md#ui-import-run-new-postgresql-entity), [UI import run.observations_unchanged](./data-model.md#ui-import-run-new-postgresql-entity), [UI import run.unresolved_observations](./data-model.md#ui-import-run-new-postgresql-entity), [UI import run.error_code](./data-model.md#ui-import-run-new-postgresql-entity), and [UI import run.error_message](./data-model.md#ui-import-run-new-postgresql-entity).
- [X] T016 [P] [US1] Add the reviewed import-run schema, checks and latest-run index in `alembic/versions/0004_ui_import_run.py` using the canonical field definitions cited in T015.
- [X] T017 [US1] Extend the shared session and public ingestion interfaces in `src/personal_financial_assistant/infrastructure/database.py` and `src/personal_financial_assistant/ingestion/service.py` for the pinned async connection and UI file-operation worker; implement the worker and its async client in `src/personal_financial_assistant/ingestion/ui_worker.py` and `src/personal_financial_assistant/ingestion/worker_client.py` with the [workbook deadlines and cleanup](./data-model.md#workbook-deadlines-and-cleanup), without silent reconnection, duplicated parser logic, or changed CLI behavior.
- [X] T018 [US1] Implement one owned import task, in-process start serialization, pinned session-level advisory lock, stale-run recovery, timeout and worker cleanup, safe shutdown, result persistence and unknown-outcome handling in `src/personal_financial_assistant/ui/import_coordinator.py` according to [run lifecycle](./data-model.md#run-lifecycle-and-ownership) and [workbook deadlines](./data-model.md#workbook-deadlines-and-cleanup).
- [X] T019 [US1] Implement folder validation and import/current status HTTP routes with sanitized responses in `src/personal_financial_assistant/ui/import_routes.py`, and register them in `src/personal_financial_assistant/ui/app.py`.
- [X] T020 [US1] Implement the local-folder form, running/result/unknown presentation, count summaries, polling, request timeout handling without automatic resubmission, and refresh reattachment in `src/personal_financial_assistant/ui/static/import.js`, following [workbook deadlines and cleanup](./data-model.md#workbook-deadlines-and-cleanup).
- [X] T021 [US1] Connect import rendering and running-state navigation blocking to `src/personal_financial_assistant/ui/static/app.js` and `src/personal_financial_assistant/ui/static/index.html`; keep navigation available after completion.
- [X] T022 [US1] Run targeted import unit, worker, HTTP, browser and PostgreSQL integration tests in `tests/unit/ui/test_import_coordinator.py`, `tests/unit/ingestion/test_ui_worker.py`, `tests/unit/ui/test_import_routes.py`, `tests/browser/test_import.py`, and `tests/integration/test_ui_imports.py`; run migration and existing ingestion regression tests in `tests/integration/test_migrations.py`, `tests/integration/test_ingestion_failures.py`, and `tests/unit/ingestion/test_service.py`.

**Checkpoint**: Import is independently usable and verified without implementing transaction browsing or chat.

## Phase 4: User Story 2 - Explore and filter recorded transactions (Priority: P1)

**Goal**: Browse occurrence-based records, inspect linked source evidence, and filter without inventing certainty or losing monetary precision.

**Independent Test**: Populate representative synthetic occurrences, apply and clear all filters, and compare pages and details with expected records, including ambiguous matches and absent observations.

### Tests for User Story 2

- [X] T023 [P] [US2] Write unit tests for exact EUR conversion, invalid ranges, status/category/text validation, 64-bit bounds and filter-bound cursors in `tests/unit/transactions/test_filters.py`, and isolated async transaction-service behavior and error paths with a mocked database boundary in `tests/unit/transactions/test_service.py`.
- [X] T024 [P] [US2] Write HTTP contract tests for transaction search, detail and categories, including sanitized errors and no financial values in URLs, in `tests/unit/ui/test_transaction_routes.py`.
- [X] T025 [P] [US2] Write real-PostgreSQL query tests in `tests/integration/test_transaction_queries.py` covering at least 100 synthetic occurrences, combined filters, literal text, distinct identical-looking occurrences, different matching observations, missing links, boundaries, pagination and empty/error distinctions.
- [X] T026 [P] [US2] Write browser tests for filtering, paging, details, uncertainty/category labels, exact amounts, request timeouts and empty/retry states in `tests/browser/test_transactions.py`.

### Implementation for User Story 2

- [X] T027 [P] [US2] Implement typed filter parsing and validation in `src/personal_financial_assistant/transactions/filters.py`, citing [Transaction filters.date_from](./data-model.md#transaction-filters-and-projections), [Transaction filters.date_to](./data-model.md#transaction-filters-and-projections), [Transaction filters.booking_status](./data-model.md#transaction-filters-and-projections), [Transaction filters.text](./data-model.md#transaction-filters-and-projections), [Transaction filters.category](./data-model.md#transaction-filters-and-projections), [Transaction filters.amount_min](./data-model.md#transaction-filters-and-projections), [Transaction filters.amount_max](./data-model.md#transaction-filters-and-projections), [Transaction filters.cursor](./data-model.md#transaction-filters-and-projections), and [Transaction filters.page_size](./data-model.md#transaction-filters-and-projections).
- [X] T028 [US2] Implement public async occurrence search, consistent history detection, linked-observation detail, category discovery and stable pagination in `src/personal_financial_assistant/transactions/service.py` and `src/personal_financial_assistant/transactions/__init__.py`; preserve [TransactionOccurrence.id](./data-model.md#existing-persisted-entities), [TransactionOccurrence.transaction_date](./data-model.md#existing-persisted-entities), [TransactionOccurrence.amount_minor](./data-model.md#existing-persisted-entities), [TransactionOccurrence.currency](./data-model.md#existing-persisted-entities), [TransactionOccurrence.booking_status](./data-model.md#existing-persisted-entities), [TransactionOccurrence.reconciliation_state](./data-model.md#existing-persisted-entities), [TransactionObservation.operation](./data-model.md#existing-persisted-entities), [TransactionObservation.details](./data-model.md#existing-persisted-entities), [TransactionObservation.category](./data-model.md#existing-persisted-entities), and [TransactionObservation.booking_status](./data-model.md#existing-persisted-entities).
- [X] T029 [US2] Implement search, detail and category HTTP contracts in `src/personal_financial_assistant/ui/transaction_routes.py` and register them in `src/personal_financial_assistant/ui/app.py`, using exact string representations and explicit errors.
- [X] T030 [US2] Implement transaction list, filter controls, pagination, observation details, safe text rendering and distinct empty/error states in `src/personal_financial_assistant/ui/static/transactions.js`.
- [X] T031 [US2] Connect the transaction screen to the shell in `src/personal_financial_assistant/ui/static/app.js` and `src/personal_financial_assistant/ui/static/index.html`, including history-not-live wording and refresh after imports.
- [X] T032 [US2] Run targeted filter and transaction-service unit, HTTP, browser and PostgreSQL tests in `tests/unit/transactions/test_filters.py`, `tests/unit/transactions/test_service.py`, `tests/unit/ui/test_transaction_routes.py`, `tests/integration/test_transaction_queries.py`, and `tests/browser/test_transactions.py`.

**Checkpoint**: Transaction exploration works independently with preloaded synthetic data and does not rely on a chat service.

## Phase 5: User Story 3 - Navigate an interface prepared for future conversation (Priority: P2)

**Goal**: Make unavailable chat the initial destination while retaining clear access to working import and transaction areas.

**Independent Test**: Open the application without a model service, verify the chat/report unavailable labels, and navigate to each available area.

### Tests for User Story 3

- [X] T033 [P] [US3] Write browser tests for the initial chat placeholder, unavailable reports, absent message/report controls, accessible navigation and operation without a model service in `tests/browser/test_navigation.py`.
- [X] T034 [P] [US3] Write focused presentation tests for safe placeholder/bootstrap behavior and the absence of chat/report endpoints in `tests/unit/ui/test_navigation.py`.

### Implementation for User Story 3

- [X] T035 [US3] Implement the unavailable chat/report presentation without sending messages or generating reports in `src/personal_financial_assistant/ui/static/chat.js`.
- [X] T036 [US3] Set chat as the initial view and integrate links to import and transactions in `src/personal_financial_assistant/ui/static/app.js` and `src/personal_financial_assistant/ui/static/index.html`, retaining the active-import navigation guard.
- [X] T037 [US3] Run navigation and integration browser tests in `tests/browser/test_navigation.py`, `tests/browser/test_import.py`, and `tests/browser/test_transactions.py` without a model service.

**Checkpoint**: All three stories operate together; unavailable future capabilities are not presented as functional.

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T038 [P] Update `README.md` and `specs/002-financial-assistant-ui/quickstart.md` with the actual uv-managed startup, migration, browser provisioning, privacy limitations and test commands, preserving existing CLI documentation.
- [X] T039 Run the end-to-end synthetic scenarios and security checks in `specs/002-financial-assistant-ui/quickstart.md`, including no external requests, no sensitive log/URL data, post-import transaction refresh, and interruption recovery.
- [ ] T040 Perform the five-person usability assessment against SC-001 and SC-005 in `specs/002-financial-assistant-ui/spec.md`; record measured outcomes or explicitly report the validation as incomplete if representative participants are unavailable.
  - Validation incomplete: five representative participants were not available; SC-001 and SC-005 have not been measured.
- [X] T041 Run full configured uv quality gates for `pyproject.toml` and `tests/`: Ruff lint and formatting, strict Pyright, and all required pytest unit, real-PostgreSQL integration, migration and browser suites; report every failure or required skip.

## Dependencies & Execution Order

### Phase Dependencies

- Setup T001-T002 precedes the foundation; T002 can be written independently of T001.
- Foundation T003-T009 precedes all story implementation. T003 and T004 can run together; T005 precedes T006, and T006 precedes T008-T009. T007 is independent of T005-T006 once setup is complete.
- US1 and US2 can develop their distinct services, tests and standalone screen files independently after the foundation. Their edits to shared `ui/app.py`, `static/app.js`, and `static/index.html` must be serialized: finish US1 T019/T021 before US2 T029/T031, or coordinate an equivalent non-conflicting integration.
- US3 presentation/tests can start after the foundation, but final navigation integration T036 and combined test T037 depend on US1 T021 and US2 T031.
- Polish and complete release validation require the three story checkpoints.

### Story Dependencies

- **US1 (P1)**: Foundation only. The import coordinator depends on the migration/model and pinned connection boundary (T015-T017 before T018; T018 before T019-T021).
- **US2 (P1)**: Foundation only for standalone behavior with preloaded data. Filter validation T027 precedes query service T028, then routes and UI; T031 also integrates with US1's completed navigation guard.
- **US3 (P2)**: Foundation for its standalone placeholder; final links and cross-story browser verification depend on US1 and US2 integration.

### Parallel Opportunities

- US1 tests T010-T014 are separate files and can be authored concurrently; its model T015 and migration T016 can be authored together after the tests are written.
- US2 tests T023-T026 are separate files and can be authored concurrently. Its filter model T027 can proceed independently of US1's coordinator once the foundation is ready.
- US3 tests T033-T034 can be authored concurrently, and its standalone `chat.js` T035 can be developed independently of story services.
- T038 can be drafted independently once the intended commands are known, then verified against the implemented behavior.

## Implementation Strategy

### MVP First

1. Complete setup and foundation.
2. Deliver US1 and run its independent tests; the shell must not claim unimplemented areas work.
3. Demonstrate folder import with safe outcomes and restart handling before adding transaction exploration.

### Incremental Delivery

1. Add US2 using preloaded synthetic records; then verify post-import refresh with US1.
2. Integrate US3 as the default placeholder, preserving the import navigation guard.
3. Complete cross-story security, migration, browser, usability and quality-gate checks. Do not treat unavailable Docker, a browser, or usability participants as passing evidence.

## Phase 7: Convergence

- [X] T042 CRITICAL: Guarantee owned workbook-worker termination and reaping after unexpected ingestion exceptions as well as cancellation, without concealing the error or accepting another import when cleanup is unconfirmed; add focused unit and subprocess cleanup tests per Constitution III and T018 (contradicts).
- [X] T043 Reject malformed or incomplete browser date inputs rather than treating an invalid date control's empty value as an omitted boundary; show an actionable error and add a real-browser regression test per FR-009, FR-010 and US2/AC2 (partial).
- [X] T044 Present a confirmed import-conflict rejection explicitly, then safely observe any active run without permanently treating the rejected request as an uncertain start; add browser and HTTP regression tests per FR-007 and US1/AC4 (partial).
- [X] T045 Distinguish confirmed storage or ownership unavailability from an indeterminate import-start outcome, with a safe explanation and recovery path while preserving fail-closed behavior for genuinely ambiguous starts; test unavailable storage, including an empty folder, per FR-004 and US1/AC8 (partial).
- [X] T046 Provide allowlisted, actionable, sanitized failure reasons when known for import errors such as inaccessible folders, malformed exports, account mismatch, or competing imports; retain unknown outcomes when rollback or commit cannot be confirmed and test the resulting presentation per FR-006 and US1/AC4 (partial).
- [X] T047 Explain that unresolved observation counts represent uncertain associations, without inventing confirmed transaction facts; add a focused browser test per FR-005 and US1/AC2 (partial).
- [X] T048 Add real-PostgreSQL integration coverage for an ambiguous ingestion commit and verify blocked starts and unknown recovery without claiming success or failure; rerun applicable quality gates per T012 and Constitution IV (partial).
- [ ] T049 Conduct the five-person usability assessment and record the measured SC-001 and SC-005 outcomes when representative participants are available; until then continue to report the assessment as incomplete per T040 (partial).

## Phase 8: Convergence

- [X] T050 Synchronize import status and enforce the in-application navigation guard across already-open browser tabs when a UI import starts or finishes in another tab; preserve fail-closed behavior when status is uncertain and add a multi-tab browser regression test per FR-019 and US1/AC6 (partial).

## Phase 9: Convergence

- [X] T051 CRITICAL: Reliably correlate an import-start request with its run before presenting that run as the request's outcome; preserve explicit uncertainty and prevent unsafe retries when a different tab's run appears while the request is pending or its response is lost, and add browser regression tests for competing and delayed outcomes per Constitution II, FR-004 and FR-020 (contradicts).
- [X] T052 Keep rejected folder-input feedback visible and actionable across background status polls without suppressing new running or uncertain import states; add a browser regression test per FR-003, T019 and T050 (partial).

## Phase 10: Convergence

- [X] T053 CRITICAL: Preserve the identity and uncertainty of an unresolved import-start request across tab closure and reopening, without persisting financial data or allowing unsafe retries; verify that a different run cannot be presented as its outcome in a browser regression test per Constitution II, FR-020 and US1/AC7 (contradicts).
- [X] T054 Recover a tracked import's recorded outcome when a newer run becomes latest, while independently enforcing the navigation and start guard for any currently running import; add browser and real-PostgreSQL regression tests per FR-019, FR-020 and T051 (partial).
- [X] T055 Present a matching confirmed running import as running while its start response is pending, while retaining the appropriate lock and uncertainty for unconfirmed outcomes; add a browser regression test per FR-004 and US1/AC1 (partial).

## Phase 11: Convergence

- [X] T056 CRITICAL: Preserve and clearly distinguish all relevant recovered import outcomes when multiple request IDs remain, including mixed success and failure after tab closure; do not silently discard or misattribute an outcome when starting another import, and add browser regression tests per Constitution II, FR-006 and T053-T054 (contradicts).
- [X] T057 Provide explicit, safe recovery for an unresolved start with no recorded run once it is established that the submitted request cannot still start or write, allowing transaction inspection and an intentional retry without claiming an outcome or automatically resubmitting; test restart and in-flight safety per FR-019, FR-020 and T045 (partial).
