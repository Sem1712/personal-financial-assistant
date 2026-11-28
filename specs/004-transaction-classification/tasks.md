---
description: "Implementation tasks for transaction classification and context"
---

# Tasks: Transaction Classification and Context

**Input**: [spec.md](./spec.md), [plan.md](./plan.md), [research.md](./research.md), [data-model.md](./data-model.md), [contract](./contracts/transaction-enrichment.md), and [quickstart.md](./quickstart.md)

**Tests**: The specification requires independent acceptance tests and measurable outcomes; the constitution requires unit, real PostgreSQL integration, migration and module-contract coverage.

**Format**: `[ID] [P?] [Story?] Description`; `[P]` means the task can run concurrently with other marked tasks at the same dependency point without editing the same files.

## Phase 1: Setup

**Purpose**: Verify the existing project and testing prerequisites; do not add dependencies or scaffold a new application.

- [X] T001 Check the existing uv configuration and quality commands in `pyproject.toml` and `README.md`; verify Docker and browser prerequisites described in `specs/004-transaction-classification/quickstart.md` and report unavailable tools without treating them as passed.

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish shared persistence for all stories before transaction-level operations.

- [X] T002 [P] Add PostgreSQL migration tests in `tests/integration/test_migrations.py` for upgrade from an empty database and representative `0004` data, untouched observations and occurrences, no inferred enrichment, restrictive occurrence references, and a downgrade that refuses to discard populated enrichment.
- [X] T003 [P] Add schema constraint tests in `tests/unit/infrastructure/test_models.py` and `tests/integration/test_enrichment_schema.py` for invalid rows, duplicate dimensions/context, missing references, exact confidence bounds and excess-precision rejection without rounding, and no silent deletion of enriched occurrences.
- [X] T004 Implement the mapped classification dimension and context entities in `src/personal_financial_assistant/infrastructure/models.py`, enforcing [data-model.md](./data-model.md) `Classification dimension.occurrence_id`, `Classification dimension.dimension`, `Classification dimension.value`, `Classification dimension.status`, `Classification dimension.source`, and `Classification dimension.confidence`; also enforce [data-model.md](./data-model.md) `Transaction context.user_annotation`, `Transaction context.user_explanation`, and `Transaction context.ai_explanation`, one context per occurrence, and restrictive occurrence references.
- [X] T005 Add reviewed migration `alembic/versions/0005_transaction_enrichment.py` after `0004_ui_import_run`, implementing [data-model.md](./data-model.md) `Classification dimension.occurrence_id`, `Classification dimension.dimension`, `Classification dimension.value`, `Classification dimension.status`, `Classification dimension.source`, and `Classification dimension.confidence`, plus [data-model.md](./data-model.md) `Transaction context.user_annotation`, `Transaction context.user_explanation`, and `Transaction context.ai_explanation`; preserve existing rows, avoid backfill, and guard against downgrade data loss.
- [X] T006 Run the focused migration and schema checks in `tests/integration/test_migrations.py`, `tests/integration/test_enrichment_schema.py`, and `tests/unit/infrastructure/test_models.py` against real testcontainers PostgreSQL; fix feature-caused failures before starting story implementation.

**Checkpoint**: Existing occurrences and observations remain unchanged, and the schema can hold independent enrichment safely.

## Phase 3: User Story 1 - Record independent classifications (Priority: P1) — MVP

**Goal**: Persist and retrieve independent transaction type, category and budget treatment, and show them read-only in transaction details.

**Independent Test**: Populate synthetic classified and unclassified occurrences, including distinct identical-looking records; independently update dimensions and inspect classification metadata in the detail view without changing bank evidence.

### Tests for User Story 1

- [X] T007 [P] [US1] Add unit tests in `tests/unit/transactions/test_enrichment.py` for supported and invalid dimension values, per-dimension metadata, omitted versus cleared fields, unclassified retrieval, confidence boundaries and excess-precision rejection without rounding, and validation before writing.
- [X] T008 [P] [US1] Add PostgreSQL integration tests in `tests/integration/test_transaction_enrichment.py` for at least 100 synthetic occurrences spanning every type and budget treatment, independent updates, identical-looking and unresolved occurrences, missing records, and preservation of original observations.
- [X] T009 [P] [US1] Extend `tests/unit/ui/test_transaction_routes.py` with contract tests for the additive detail enrichment object, explicit unclassified values, existing request/error behavior, and unchanged search results.
- [X] T010 [P] [US1] Extend `tests/browser/test_transactions.py` with read-only detail checks for all classification dimensions and missing metadata, no new list fields or editing controls, accessible navigation, and unchanged bank-suggestion labeling.

### Implementation for User Story 1

- [X] T011 [US1] Add typed partial-update and result validation in `src/personal_financial_assistant/transactions/enrichment.py`, implementing [data-model.md](./data-model.md) `Classification dimension.occurrence_id`, `Classification dimension.dimension`, `Classification dimension.value`, `Classification dimension.status`, `Classification dimension.source`, and `Classification dimension.confidence`, with the exact decimal-string contract in `specs/004-transaction-classification/contracts/transaction-enrichment.md`.
- [X] T012 [US1] Implement async occurrence-scoped dimension updates and retrieval in `src/personal_financial_assistant/transactions/enrichment.py`: validate the full patch first, distinguish omitted from clear, return explicit errors, lock the occurrence with the specified timeout, and commit all supplied changes atomically without changing source observations.
- [X] T013 [US1] Export the typed enrichment update and result types from `src/personal_financial_assistant/transactions/__init__.py`; preserve existing public transaction imports.
- [X] T014 [US1] Extend `src/personal_financial_assistant/transactions/service.py` to return the contract's complete unclassified or populated dimensions and context fields (null until populated), with a coherent occurrence/observation/enrichment snapshot, while preserving the existing search and category behavior.
- [X] T015 [US1] Extend `src/personal_financial_assistant/ui/transaction_routes.py` to expose the additive detail response from the public transactions boundary without adding an editing endpoint or changing existing sanitized error behavior.
- [X] T016 [US1] Render read-only classification values and metadata safely in the detail panel in `src/personal_financial_assistant/ui/static/transactions.js` and, only if needed, `src/personal_financial_assistant/ui/static/index.html` and `src/personal_financial_assistant/ui/static/styles.css`; explain excluded budget treatment and retain existing keyboard, loading and retry behavior.
- [X] T017 [US1] Run the US1 unit, route, PostgreSQL and browser tests in `tests/unit/transactions/test_enrichment.py`, `tests/unit/ui/test_transaction_routes.py`, `tests/integration/test_transaction_enrichment.py`, and `tests/browser/test_transactions.py`; verify the 100-occurrence reference set and report any unavailable prerequisites.

**Checkpoint**: US1 is demonstrable without a classifier or edit UI; original imported evidence and list behavior are unchanged.

## Phase 4: User Story 2 - Understand and correct classification evidence (Priority: P1)

**Goal**: Retain and accurately present each classification's provenance, confidence and status through user corrections and allowed automated replacements.

**Independent Test**: Submit classifications with mixed AI, rule and user sources and statuses, then replace a confirmed user value with an automated one; verify metadata, invalid-input failures and unchanged unrelated dimensions.

### Tests for User Story 2

- [X] T018 [P] [US2] Add `tests/unit/transactions/test_enrichment_provenance.py` to cover all sources and statuses, missing and boundary confidence, excess precision, invalid metadata, complete metadata replacement, sanitized errors and unknown commit outcomes.
- [X] T019 [P] [US2] Add PostgreSQL concurrency and rollback cases in `tests/integration/test_enrichment_concurrency.py` for disjoint and same-field writers, lock timeout, conflicting ingestion, cancellation, invalid multi-field updates, and confirmed rollback versus unknown commit outcome.
- [X] T020 [P] [US2] Add `tests/browser/test_enrichment_provenance.py` and `tests/unit/ui/test_enrichment_detail.py` with mixed-source and missing-confidence presentation, safe rendering of hostile category text, existing source observations and explicit detail-retrieval failure.

### Implementation for User Story 2

- [X] T021 [US2] Complete replacement, cancellation, five-second lock timeout and commit-outcome error handling in `src/personal_financial_assistant/transactions/enrichment.py` according to [data-model.md](./data-model.md) `Classification dimension.status`, `Classification dimension.source`, and `Classification dimension.confidence`; allow valid automated replacement of confirmed user values and never retain stale metadata.
- [X] T022 [US2] Complete source/status/confidence labeling and safe text rendering in `src/personal_financial_assistant/ui/static/transactions.js`, preserving separate bank evidence and reporting failed detail retrieval without presenting missing data as a successful response.
- [X] T023 [US2] Run the provenance and concurrency checks in `tests/unit/transactions/test_enrichment_provenance.py`, `tests/integration/test_enrichment_concurrency.py`, `tests/unit/ui/test_enrichment_detail.py`, and `tests/browser/test_enrichment_provenance.py`; confirm disjoint updates survive and same-field committed updates follow the documented order.

**Checkpoint**: Sources and uncertainty are distinguishable, replacement follows the user's chosen policy, and errors do not imply success.

## Phase 5: User Story 3 - Retain context and original evidence (Priority: P2)

**Goal**: Store and display independent user notes and user/AI explanations while preserving all imported evidence through reimport and reconciliation.

**Independent Test**: Record and independently clear context, then reimport synthetic overlapping data and reconcile pending to booked; verify enrichment remains attached to the same occurrence and bank observations remain unchanged.

### Tests for User Story 3

- [X] T024 [P] [US3] Add unit cases in `tests/unit/transactions/test_enrichment_context.py` for independent add/change/clear of all context fields, simultaneous user and AI explanations, rejection of rule explanations and all-or-nothing invalid patches.
- [X] T025 [P] [US3] Extend `tests/integration/test_ingestion_reconciliation.py` with five repeated overlapping imports, confirmed pending-to-booked reconciliation, ambiguous matches and conflicting bank categories; assert occurrence identity, existing observation evidence and enrichment preservation without cross-occurrence transfer.
- [X] T026 [P] [US3] Add browser cases in `tests/browser/test_enrichment_context.py` for separate labels, missing context, independent user/AI explanations, text injection safety, no note editing and unchanged retry behavior.

### Implementation for User Story 3

- [X] T027 [US3] Extend the typed patch and atomic update in `src/personal_financial_assistant/transactions/enrichment.py` for [data-model.md](./data-model.md) `Transaction context.user_annotation`, `Transaction context.user_explanation`, and `Transaction context.ai_explanation`; preserve each independently, reject rule explanations and avoid logging note content.
- [X] T028 [US3] Extend `src/personal_financial_assistant/transactions/service.py` and `src/personal_financial_assistant/ui/transaction_routes.py` to return all context fields with the coherent detail snapshot and existing bank observations, without changing search/list/filter contracts.
- [X] T029 [US3] Display user annotation and separately labeled user and AI explanations with explicit absence in `src/personal_financial_assistant/ui/static/transactions.js`, using text-only DOM rendering and no editing controls.
- [X] T030 [US3] Create `tests/fixtures/enrichment_demo.py` and extend `tests/integration/test_ui_browser_e2e.py` for a synthetic, read-only UI exercise: own and migrate a disposable testcontainers PostgreSQL instance, override any application database setting, populate classified and unclassified occurrences, serve the real UI on loopback port 8765, fail explicitly if occupied, and clean up on shutdown or startup failure. Test source separation, unchanged observations, no external financial-data requests and isolation from any configured application database.
- [X] T031 [US3] Run the context, reconciliation and browser checks in `tests/unit/transactions/test_enrichment_context.py`, `tests/integration/test_ingestion_reconciliation.py`, `tests/browser/test_enrichment_context.py`, and `tests/integration/test_ui_browser_e2e.py`; report unavailable services and skipped checks.

**Checkpoint**: Context is independently retained, displayed and isolated from source observations across imports.

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T032 Update `README.md` to document read-only detail enrichment, source and uncertainty labels, automatic replacement policy, the public in-process update boundary, local privacy and the absence of edit/classifier/budget features.
- [ ] T033 Execute the five-person task exercise described in `specs/004-transaction-classification/quickstart.md` and record results against SC-005: at least four of five identify bank suggestions versus classification, source and uncertainty, and excluded treatment; report an unavailable exercise or unmet threshold rather than marking it passed.
  - Not performed: five representative participants are not available in this session.
- [X] T034 Run all focused commands in `specs/004-transaction-classification/quickstart.md`, then `uv run --locked ruff check .`, `uv run --locked ruff format --check .`, `uv run --locked pyright`, and `uv run --locked pytest` from `pyproject.toml`; record failures, skipped required tests and missing infrastructure explicitly.

## Dependencies & Execution Order

### Phase Dependencies

- Setup T001 precedes foundational work. T002 and T003 can run together; both precede implementation T004 and T005, which touch different files but should be reviewed together. T006 verifies the complete foundation.
- US1 depends on the foundation; its tests T007–T010 are independent and can be authored in parallel before T011–T016. T012 follows T011, T013–T015 follow the public service/data boundary, and T016 follows the detail contract.
- US2 depends on the US1 boundary and display, and US3 depends on the US1 boundary and detail read. Complete US2 before US3 when editing their shared `enrichment.py`, `service.py`, routes, or `transactions.js`; tests in distinct files can be prepared concurrently.
- The final phase follows all stories. T033 requires representative participants; if unavailable, record it as unverified, not passed.

### User Story Dependencies

- **US1 (P1)**: Foundation only; constitutes the independently testable MVP.
- **US2 (P1)**: Builds on US1's update and detail contract; independently test provenance and replacement using seeded transactions.
- **US3 (P2)**: Builds on US1's shared boundary and persistence; independently test context and source preservation using synthetic imports.

### Parallel Opportunities

- Foundation: T002 and T003 use separate test files.
- US1: T007, T008, T009 and T010 use separate files and can be written together.
- US2: T018, T019 and T020 use separate files and can be written together once their shared boundary is defined.
- US3: T024, T025 and T026 use separate files and can be written together; sequence later edits to files shared with US2.

## Parallel Examples

### User Story 1

Prepare T007's unit validation cases, T008's real PostgreSQL reference set, T009's route contract cases and T010's browser detail cases concurrently; integrate implementations after their tests are in place.

### User Story 2

Prepare T018's provenance cases, T019's concurrent writer cases and T020's presentation cases concurrently; integrate T021 and T022 after US1.

### User Story 3

Prepare T024's context cases, T025's import/reconciliation cases and T026's browser cases concurrently; integrate T027–T030 after shared-file edits from US2.

## Implementation Strategy

1. Complete setup and shared persistence, including real migration validation.
2. Deliver US1 and independently verify the classification model and read-only detail view as the MVP.
3. Deliver US2 provenance/replacement behavior, then US3 contextual evidence and import retention; verify each separately.
4. Complete documentation, the required representative-user exercise and the full configured quality gates. Never claim skipped or unavailable checks passed.

## Phase 7: Convergence

- [X] T035 Sanitize typed enrichment validation failures so errors and logs never expose supplied notes or other raw financial payloads, while retaining actionable validation reasons; add focused tests for invalid multi-field patches per FR-015 (contradicts).
- [X] T036 Align category validation across the typed boundary, PostgreSQL and read-only detail rendering so every accepted category can be retrieved without a false detail failure, including Unicode whitespace edge cases; add focused cross-layer tests per FR-003 and FR-016 (contradicts).
- [X] T037 Extend the 100-occurrence reference-set assertions to verify every dimension's value, status, source and confidence exactly, and test that automated replacement updates status and clears or replaces previously populated confidence per SC-001, US2/AC3 and T018 (partial).
- [ ] T038 Conduct the five-person representative-user exercise and record whether at least four participants meet its criteria; report unavailability or an unmet threshold without claiming success per T033 and plan: verification (missing).

## Phase 8: Convergence

- [X] T039 Extend `tests/integration/test_ingestion_reconciliation.py` to snapshot and compare all populated classification values, statuses, sources and confidence, all context fields, and original observation fields across five overlapping imports and pending-to-booked reconciliation, allowing only specified booking-state changes per SC-003 and FR-013 (partial).
- [ ] T040 Conduct the representative-user exercise with at least five participants and record whether at least four meet all criteria; report unavailability or an unmet threshold without claiming success per SC-005 and T033 (missing).
  - Not performed: five representative participants are not available in this session.

## Phase 9: Convergence

- [ ] T041 Conduct and record the five-person representative-user exercise, including whether at least four meet every criterion, without claiming success if unavailable or unmet per SC-005, T033, T038 and T040 (missing).
