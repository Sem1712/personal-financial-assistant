---
description: "Implementation tasks for merchant identification and reusable classification rules"
---

# Tasks: Merchant Identification and Classification Rules

**Input**: Design documents from `specs/005-merchant-classification-rules/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contract](./contracts/merchant-rules.md), [quickstart.md](./quickstart.md)

**Tests**: The constitution and feature acceptance criteria require deterministic unit tests and PostgreSQL integration tests. Write focused tests before the corresponding implementation.

**Organization**: Tasks are grouped by user story; explicit dependencies below reflect shared matching, classification and AI-safety behavior. No rule-management UI or new model calls are in scope.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel with other marked tasks in the same dependency-ready group; tasks do not edit the same files.
- **[Story]**: Maps to the corresponding user story in the specification.
- Paths are repository-relative; field citations refer to the canonical constraints in [data-model.md](./data-model.md).

## Phase 1: Setup

**Purpose**: Establish the new module without adding dependencies or changing existing configuration.

- [X] T001 Create the rules package boundary in `src/personal_financial_assistant/rules/__init__.py` and the test package in `tests/unit/rules/__init__.py`; keep automated rule mutation unavailable until the safeguards in US3 exist.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish shared persistence, transaction boundaries and safe validation used by every story.

- [X] T002 [P] Add PostgreSQL migration tests in `tests/integration/test_migrations.py` for empty and populated `0006` schemas, preserved observations/enrichment/UI runs, no backfill and guarded downgrade with feature data.
- [X] T003 [P] Add focused unit tests in `tests/unit/rules/test_validation.py` for normalized nonempty text, category validation, invalid Unicode, forwarded AI provenance, unknown provenance rejection, safe errors and unknown commit outcomes.
- [X] T004 Implement merchant and reusable-rule mappings and constraints in `src/personal_financial_assistant/infrastructure/models.py` using [data-model.md](./data-model.md#merchant-and-reusable-rules): `Merchant.canonical name`, `Merchant.enabled state`, `Merchant.revision`; `Matching entry.merchant ID`, `Matching entry.kind`, `Matching entry.original text`, `Matching entry.normalized text`, `Matching entry.origin`, `Matching entry.confirmed`, `Matching entry.enabled`, `Matching entry.revision`; `Merchant default.merchant ID`, `Merchant default.category`, `Merchant default.origin`, `Merchant default.confirmed`, `Merchant default.enabled`, `Merchant default.revision`; and `Classification preference.match kind`, `Classification preference.merchant ID`, `Classification preference.match text`, `Classification preference.category`, `Classification preference.origin`, `Classification preference.confirmed`, `Classification preference.enabled`, `Classification preference.revision`.
- [X] T005 Implement override, change-suggestion and review mappings and constraints in `src/personal_financial_assistant/infrastructure/models.py` using [data-model.md](./data-model.md#transaction-override): `Transaction override.occurrence ID`, `Transaction override.category`, `Transaction override.revision`; and [data-model.md](./data-model.md#suggestions-conflicts-and-approvals): `Change suggestion.target type/ID`, `Change suggestion.target revision`, `Change suggestion.proposed action`, `Change suggestion.validated payload`, `Change suggestion.origin`, `Change suggestion.state`, `Change suggestion.review snapshot`, `Application conflict.occurrence ID`, `Application conflict.AI entry kind/ID/revision`, `Application conflict.confirmed entry kind/ID/revision`, `Application conflict.evidence revision`, `Application conflict.outcome kind`, `Application conflict.state`, `Application conflict.review snapshot`, `Application approval.Conflict ID` and `Application approval.reviewed entry revisions/evidence revision`.
- [X] T006 Implement rules-configuration locking and evaluation-work mappings in `src/personal_financial_assistant/infrastructure/models.py` using [data-model.md](./data-model.md#evaluation-and-durable-work): `Occurrence evidence revision.Occurrence ID`, `Occurrence evidence revision.revision`, `Import evaluation work.Occurrence ID`, `Import evaluation work.import correlation ID`, `Import evaluation work.state`, `Import evaluation work.last sanitized error code`, `Import evaluation work.latest evaluation result`, `Evaluation outcome.Occurrence ID`, `Evaluation outcome.evidence revision`, `Evaluation outcome.identified merchant ID`, `Evaluation outcome.matching candidates`, `Evaluation outcome.category decision`, `Evaluation outcome.winning rule/override references`, `Evaluation outcome.blocked AI conflicts` and `Evaluation outcome.status`.
- [X] T007 Create `alembic/versions/0007_merchant_rules.py` after `0006_category_whitespace` for the T004–T006 mappings, foreign keys, checks, singleton configuration row, supported-schema preservation, no backfill and guarded downgrade; update revision expectations in `tests/integration/test_migrations.py`.
- [X] T008 Extract a public, session-composable occurrence/category update and lock boundary in `src/personal_financial_assistant/transactions/enrichment.py` and `src/personal_financial_assistant/transactions/__init__.py`, preserving the existing `update_enrichment` behavior and avoiding nested commits.
- [X] T009 Implement typed rule inputs/results, kind-qualified rule references, Unicode-safe validation, generation provenance preserved across services and sanitized error types in `src/personal_financial_assistant/rules/types.py`, following [data-model.md](./data-model.md) and [merchant-rules.md](./contracts/merchant-rules.md).
- [X] T010 Implement shared async configuration/occurrence locking, five-second timeout, rollback, cancellation and unknown-commit handling in `src/personal_financial_assistant/rules/storage.py`, using the lock order in [data-model.md](./data-model.md#transaction-concurrency-and-failure-invariants).

**Checkpoint**: Schema and shared primitives are available; existing enrichment behavior remains intact. No AI mutation or evaluation entry point is exposed without its protection.

---

## Phase 3: User Story 1 - Identify merchants consistently (Priority: P1) 🎯 MVP

**Goal**: Create and inspect merchants, aliases and literal patterns and resolve linked descriptions without modifying bank evidence.

**Independent Test**: Create a merchant with an alias and a pattern, evaluate synthetic occurrences, and verify resolved/no-match/conflict outcomes alongside unchanged original observations.

### Tests for User Story 1

- [X] T011 [P] [US1] Add at least 100 synthetic description cases in `tests/unit/rules/test_matching.py` for Unicode case-folding, whitespace, exact versus substring precedence, no linked text, multiple fields and same/different-merchant ties.
- [X] T012 [P] [US1] Add PostgreSQL merchant management and matching contract tests in `tests/integration/test_merchant_rules.py`, including disabled entries, duplicate validation, linked observations and unchanged source data.

### Implementation for User Story 1

- [X] T013 [US1] Implement pure normalization and deterministic per-field alias/substring merchant matching in `src/personal_financial_assistant/rules/matching.py`, following [data-model.md](./data-model.md#evaluation-rules).
- [X] T014 [US1] Implement user-directed merchant and matching-entry create, inspect, edit, enable/disable and explicit confirmation in `src/personal_financial_assistant/rules/merchants.py`, including revision checks and the T004 field constraints.
- [X] T015 [US1] Implement occurrence-based merchant identification and typed resolved/no-match/conflict results in `src/personal_financial_assistant/rules/evaluation.py`, using linked observations and the shared locks without changing source records.
- [X] T016 [US1] Export the user-directed merchant and identification operations through `src/personal_financial_assistant/rules/__init__.py`; keep AI-originated rule creation/editing unavailable until T030–T033.

**Checkpoint**: US1 is independently testable with user-directed entries; the incremental MVP does not expose unprotected AI mutation.

---

## Phase 4: User Story 2 - Apply reusable category rules (Priority: P1)

**Goal**: Apply merchant defaults and classification preferences with transaction-specific overrides and explicit precedence.

**Independent Test**: Evaluate a merchant default, a matching preference and a single-occurrence override, including same-rank conflict and unchanged prior category on no match.

### Tests for User Story 2

- [X] T017 [P] [US2] Add deterministic precedence and tie tests in `tests/unit/rules/test_categories.py` for all specificity levels, same/different-category ties, ambiguous merchants, no rule, provenance and confidence.
- [X] T018 [P] [US2] Add PostgreSQL default, preference and override contract cases in `tests/integration/test_merchant_rule_categories.py` covering atomic set/change/clear, unrelated dimensions, duplicate-looking occurrences and existing general enrichment updates.

### Implementation for User Story 2

- [X] T019 [US2] Implement user-directed merchant-default and classification-preference create, inspect, edit, enable/disable and explicit confirmation in `src/personal_financial_assistant/rules/categories.py`, using the T004 field constraints and revision checks.
- [X] T020 [US2] Implement occurrence override set/inspect/change/clear in `src/personal_financial_assistant/rules/overrides.py` and the session-composable transaction boundary from T008; atomically update category with user provenance while preserving other fields.
- [X] T021 [US2] Extend `src/personal_financial_assistant/rules/evaluation.py` to select overrides, preferences and defaults in specified order, preserve existing values on ambiguity/no match, and atomically write rule-sourced category/status without invented confidence.
- [X] T022 [US2] Export user-directed category-rule and override operations in `src/personal_financial_assistant/rules/__init__.py`; preserve existing generic `transactions.update_enrichment` replacement semantics.

**Checkpoint**: User-directed category rules and per-occurrence overrides are independently testable; automated proposals remain gated.

---

## Phase 5: User Story 3 - Maintain rules without losing confirmed decisions (Priority: P1)

**Goal**: Enable automated rule proposals and explicit user review without silently modifying or bypassing confirmed decisions.

**Independent Test**: Confirm rules, submit AI changes and overlapping suggestions, then approve/reject specific applications and verify persisted state and provenance.

### Tests for User Story 3

- [X] T023 [P] [US3] Add unit cases in `tests/unit/rules/test_review.py` for preserved generation provenance, AI proposals forwarded/transformed by a service, unknown provenance rejection, explicit confirmation, stale review, rejection and scoped approval without bypassing normal precedence.
- [X] T024 [P] [US3] Add at least 20 synthetic protection attempts in `tests/integration/test_merchant_rules_review.py` for direct/indirect edits, per-occurrence conflicts, multiple confirmed rules, colliding IDs across rule kinds, non-conflicting applications and explicit approval/rejection.
- [X] T025 [P] [US3] Add PostgreSQL race tests in `tests/integration/test_merchant_rules_concurrency.py` and `tests/integration/test_rules_storage.py` for confirmation versus evaluation, stale previews after new applicable rules or override/category/evidence changes, lock timeout, cancellation and unknown commit.

### Implementation for User Story 3

- [X] T026 [US3] Implement automated proposal operations and pending AI changes to confirmed entries or indirectly disabled merchants in `src/personal_financial_assistant/rules/proposals.py`, preserving trusted generation provenance across services and rejecting unknown origin.
- [X] T027 [US3] Implement application-conflict detection, reporting and per-occurrence block decisions with kind-qualified entry references before merchant and category precedence in `src/personal_financial_assistant/rules/conflicts.py`, using [data-model.md](./data-model.md#suggestions-conflicts-and-approvals).
- [X] T028 [US3] Implement inspect/preview/approve/reject for change suggestions and application conflicts in `src/personal_financial_assistant/rules/review.py`, recomputing the full reviewed snapshot under locks and enforcing typed pair-scoped approval and stale-review rejection.
- [X] T029 [US3] Integrate T027–T028 into `src/personal_financial_assistant/rules/evaluation.py` and `src/personal_financial_assistant/rules/merchants.py`, retaining normal precedence after approval and invalidating stale approvals after relevant changes.
- [X] T030 [US3] Integrate T027–T028 into `src/personal_financial_assistant/rules/categories.py` and `src/personal_financial_assistant/rules/proposals.py`, protecting confirmed category rules regardless of specificity and enabling safe non-conflicting proposals.
- [X] T031 [US3] Export separate trusted user-directed and automated proposal/review operations in `src/personal_financial_assistant/rules/__init__.py`, without accepting model-supplied confirmation or user authority.
- [X] T032 [US3] Verify current merchant and category public operations in `src/personal_financial_assistant/rules/merchants.py` and `src/personal_financial_assistant/rules/categories.py` take the configuration lock and protect confirmed entries for every automated mutation.
- [X] T033 [US3] Integrate explicit application-review outcomes and rejection persistence in `src/personal_financial_assistant/rules/evaluation.py`, ensuring every typed blocked pair is reported and full review snapshots are rechecked atomically.

**Checkpoint**: Full rule maintenance and AI conflict protections are operational through service-level interactions; no browser rule controls exist.

---

## Phase 6: User Story 4 - Explain and control reclassification (Priority: P2)

**Goal**: Evaluate newly imported occurrences automatically and explicitly reapply rules to selected existing occurrences, preserving imports across evaluation failures.

**Independent Test**: Change a rule, reapply to selected synthetic occurrences with and without overrides, and import new/overlapping data while checking per-occurrence outcomes and retry behavior.

### Tests for User Story 4

- [X] T034 [P] [US4] Add unit tests in `tests/unit/rules/test_reapplication.py` for selected IDs, duplicate/empty input, per-occurrence outcomes, retry eligibility and preserved override/category behavior.
- [X] T035 [P] [US4] Add PostgreSQL import tests in `tests/integration/test_merchant_rules_import.py` for new, unresolved, overlapping and pending-to-booked occurrences; assert completed outcomes for every new occurrence when evaluation succeeds and individually inspectable failed/pending/unknown outcomes otherwise, preserving imported data and existing classifications; cover concurrent evidence linking, interruption, retry and duplicate prevention.
- [X] T036 [P] [US4] Add CLI result and sanitized warning tests in `tests/unit/cli/test_ingest_command.py` for successful import with incomplete, failed or unknown evaluation.
- [X] T037 [P] [US4] Add import-status and warning regression tests in `tests/unit/ui/test_import_coordinator.py`, `tests/unit/ui/test_import_routes.py` and `tests/browser/test_import.py`, preserving existing states, navigation and accessibility behavior.
- [X] T038 [P] [US4] Add at least 50 selected/unselected occurrence cases in `tests/integration/test_merchant_rules_reapplication.py` for overrides, conflicts, explanation, individual failures and untouched source/other dimensions.

### Implementation for User Story 4

- [X] T039 [US4] Extend `src/personal_financial_assistant/ingestion/service.py` to lock existing occurrences before linking or booking updates, increment evidence revisions only when links change, and enqueue unique pending work for every newly created occurrence in the atomic import transaction.
- [X] T040 [US4] Implement bounded sequential selected reapplication, durable work inspection and explicit pending/failed retry in `src/personal_financial_assistant/rules/work.py`; atomically persist evaluation, conflict and work completion, and distinguish failed rollback from unknown commit.
- [X] T041 [US4] Extend `src/personal_financial_assistant/ingestion/service.py` to assign import correlation IDs and call the public rules boundary after import commit, retain committed bank data on evaluation failure, and return separate per-occurrence and aggregate evaluation statuses.
- [X] T042 [US4] Export work inspection, explicit reapplication and retry through `src/personal_financial_assistant/rules/__init__.py`, including pinned-connection ownership and no nested transaction commits.
- [X] T043 [US4] Extend `src/personal_financial_assistant/cli.py` with sanitized evaluation warnings while preserving existing import counts and reporting committed import separately from classification failure.
- [X] T044 [US4] Update `src/personal_financial_assistant/ui/import_coordinator.py`, `src/personal_financial_assistant/ui/import_routes.py` and `src/personal_financial_assistant/ui/static/import.js` to correlate UI runs, persist or derive warning summaries and expose additive sanitized status without introducing rule controls.
- [X] T045 [US4] Complete restart and failure recovery in `src/personal_financial_assistant/rules/work.py` and `src/personal_financial_assistant/ingestion/service.py`: leave interrupted work discoverable, report status-write failure explicitly, and require state inspection before retrying unknown outcomes.

**Checkpoint**: Imports and selected reapplication report explainable outcomes; evaluation failure never undoes a successful import and work remains recoverable.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Verify the complete feature, privacy and directly affected documentation.

- [X] T046 [P] Update `README.md` for rule management boundaries, new-occurrence evaluation, override behavior, review safeguards, warnings, recovery and local-data constraints; update test selectors in `specs/005-merchant-classification-rules/quickstart.md` for all implemented focused test files.
- [X] T047 [P] Add end-to-end privacy and public-contract regression cases in `tests/integration/test_merchant_rules.py` and `tests/unit/rules/test_validation.py` for sanitized errors/logs, no raw payload leakage, service-only management and explicit no-match/conflict outcomes.
- [X] T048 Run the focused commands and synthetic end-to-end scenarios in `specs/005-merchant-classification-rules/quickstart.md`; verify SC-001–SC-006, both migration starting states and guarded downgrade, and report any unavailable prerequisites.
- [X] T049 Run `uv run --locked ruff check .`, `uv run --locked ruff format --check .`, `uv run --locked pyright` and `uv run --locked pytest` from `pyproject.toml`; report all failed or skipped required checks rather than treating missing Docker or browser prerequisites as success.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup → Foundation**: T001 precedes T002–T010. In Foundation, T002/T003 can be authored together; T004 → T005 → T006 → T007 serialize shared schema edits. T008–T010 depend on the relevant foundation definitions.
- **US1 → US2 → US3 → US4**: US2 consumes US1 identification; US3 protects both matching and categories; US4 runs the protected full evaluator after import. Tests for a later story may be authored earlier only when they do not depend on unavailable APIs or edit the same file.
- **Polish**: T046/T047 are independent after story implementation; T048 follows both and all story checkpoints; T049 follows T048.

### Story Dependencies and Independent Checks

- **US1 (P1)**: Foundation only. Create merchant + alias/pattern and verify identification and unchanged source observations. This is the safe user-directed MVP; AI entry points are deferred to US3.
- **US2 (P1)**: Requires US1 identification. Verify default, preference, override, ties and no-match against synthetic occurrences.
- **US3 (P1)**: Requires US1/US2 rule/evaluation boundaries. Verify protected AI edits and per-occurrence conflict review without modifying confirmed records.
- **US4 (P2)**: Requires US1–US3. Verify automatic new-occurrence evaluation, explicit reapplication and failure/retry without undoing imports.

### Within Each User Story

- Write and observe focused failing tests before implementation; models and migrations precede services, and services precede import integration.
- An individual outcome is atomic; a selected batch is not. Preserve all unrelated classifications, source observations and financial facts.
- No [P] tasks edit the same file within their listed parallel group; do not parallelize tasks that modify shared model, migration, evaluator or package-export files.

## Parallel Examples

### User Story 1

- After Foundation, write T011 `tests/unit/rules/test_matching.py` and T012 `tests/integration/test_merchant_rules.py` concurrently.

### User Story 2

- After US1, write T017 `tests/unit/rules/test_categories.py` and T018 `tests/integration/test_merchant_rule_categories.py` concurrently.

### User Story 3

- After US2, write T023 `tests/unit/rules/test_review.py`, T024 `tests/integration/test_merchant_rules_review.py` and T025 `tests/integration/test_merchant_rules_concurrency.py` concurrently.

### User Story 4

- After US3, write T034–T038 concurrently: each task owns different unit, integration, CLI or UI test files.

## Implementation Strategy

### MVP First

1. Complete setup and foundation, then US1.
2. Validate merchant identification against its independent test; expose only user-directed rule management until AI safeguards are implemented.
3. This MVP is an incremental demonstration, not completion of the full feature.

### Incremental Delivery

1. Add US2 category precedence and overrides; verify its independent test.
2. Add US3 automated proposals and confirmed-rule safeguards; verify conflicts and scoped approvals before exposing automated operations.
3. Add US4 post-commit import evaluation and explicit reapplication; verify recovery and import preservation.
4. Complete cross-cutting documentation, focused checks and all configured release gates.

## Notes

- Use uv for execution, pytest-asyncio for async behavior and testcontainers PostgreSQL for database integration and migrations; never substitute SQLite.
- Do not log descriptions, financial payloads, notes, credentials or suggestion payloads. Treat an unknown commit outcome as unknown, not as success or rollback.
- Source observations and existing reconciliation semantics remain authoritative; no agent provider, analytics, budget calculation or user-facing rule-management controls are added.

## Phase 8: Convergence

- [X] T050 CRITICAL: Preserve cancellation during rule-evaluation commits and stop processing subsequent occurrences in `src/personal_financial_assistant/rules/storage.py` and `src/personal_financial_assistant/rules/work.py`, while explicitly retaining unknown-commit inspection and recovery semantics; add focused cancellation-during-commit tests for retry, reapplication and import per Constitution III and T010/T040 (contradicts).
- [X] T051 Persist and expose the complete merchant decision, including winning or conflicting matching entries, and all category-conflict candidates in durable import evaluation outcomes; add PostgreSQL tests comparing inspected outcomes with returned results, and update the schema and migration if necessary per FR-008, FR-015 and T006 (partial).
- [ ] T052 Report unexpected post-commit evaluation failures separately from committed imports, with sanitized diagnostics and individually inspectable recoverable work, without concealing programming errors or cancellation; add focused service, CLI and UI failure-path tests per FR-014 and US4/AC6 (partial).

## Phase 9: Convergence

- [ ] T053 Complete the remaining T052 post-commit failure-reporting path: preserve and report the committed import separately from unexpected evaluation errors, expose affected recoverable work, and verify sanitized service, CLI and UI behavior without concealing programming errors or cancellation per FR-014 and US4/AC6 (partial).
