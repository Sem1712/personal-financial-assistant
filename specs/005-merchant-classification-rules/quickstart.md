# Quickstart: Merchant Rules Validation

Use synthetic data only. See [contract](./contracts/merchant-rules.md) and [data model](./data-model.md) for precise inputs, output and recovery semantics.

## Prerequisites

- Python 3.15+, uv and the project's locked dependencies.
- A working Docker daemon for PostgreSQL testcontainers; a missing daemon is a failed prerequisite, not a passing integration check.
- No local model server or live financial data is required. All test observations, proposals and review actions are controlled.

## Focused validation

Run the focused checks:

```sh
uv run --locked pytest tests/unit/rules tests/unit/ingestion tests/unit/cli/test_ingest_command.py tests/unit/ui/test_import_coordinator.py tests/unit/ui/test_import_routes.py
uv run --locked pytest tests/integration/test_merchant_rules.py tests/integration/test_merchant_rules_review.py tests/integration/test_merchant_rules_concurrency.py tests/integration/test_application_review.py tests/integration/test_rule_change_review.py tests/integration/test_rule_conflicts.py tests/integration/test_rule_proposals.py tests/integration/test_merchant_rule_categories.py tests/integration/test_merchant_rules_import.py tests/integration/test_merchant_rules_reapplication.py tests/integration/test_rule_work.py tests/integration/test_migrations.py
uv run --locked pytest tests/browser/test_import.py
```

The new tests must cover:

1. At least 100 synthetic description cases, including exact versus substring matching, Unicode case and whitespace normalization, multiple linked observations, blank/no linked text and ambiguous merchants.
2. All category precedence levels, same-rank same/different categories, merchant ambiguity, no-match preservation, and 50 selected/unselected occurrences with overrides. Verify unaffected type, budget treatment, notes and original observations.
3. At least 20 AI changes or conflicting applications against confirmed decisions, plus non-conflicting applications; include AI output forwarded/transformed by a classification service and unknown provenance. Verify kind-qualified references when a default and preference share a numeric ID, explicit per-occurrence/per-pair approval, rejection and multiple conflicts. Before approval, add a relevant rule or change an override/current category or linked evidence and verify stale previews are rejected; also test concurrency with confirmation.
4. New imports, overlapping imports and pending-to-booked reconciliation: only new occurrences receive automatic work. For successful evaluations all new occurrences have completed outcomes; on injected failures each affected occurrence is reported as failed, pending or unknown without undoing the import. Include unresolved occurrences, process interruption with pending work, explicit retry, unknown commit and duplicate/replay prevention.
5. Migration upgrade on empty PostgreSQL and on a populated `0006` schema containing representative observations, enrichments and UI import runs, plus guarded downgrade with feature data. Verify sanitized error/output behavior and additive CLI/UI status warnings.

`rules.inspect_work` without a filter lists recoverable work after interruption;
use its state before explicitly retrying pending or failed occurrence IDs.
Reapplication and retry selections are limited to 500 distinct occurrence IDs.

Then run the existing quality gates:

```sh
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pyright
uv run --locked pytest
```

The full suite may need the project's browser prerequisites in addition to Docker. Report any missing or skipped required checks rather than claiming they passed.

## Service-level acceptance flow

With a migrated disposable PostgreSQL test database, use the public async rules boundary to create an enabled merchant, exact alias and literal substring pattern; create and explicitly confirm a merchant default; and create a conflicting AI preference. Import synthetic occurrences through the existing ingestion entry point. Inspect the returned import summary and stored evaluation outcomes: new occurrences are evaluated, source descriptions are unchanged, the confirmed decision is protected on conflicting occurrences, and non-conflicting AI applications remain eligible. Review and approve one occurrence-specific conflict; verify its preview and normal priority outcome. Set a user override, reapply to a selected set, and verify that the override and unselected transactions are unchanged.

Inject a confirmed evaluation failure after import commit and verify that the bank data remains, the affected occurrence is reported, and a selected explicit retry can complete. Simulate interruption after commit and inspect durable pending work. For a lost commit acknowledgement, inspect current state before retrying; do not assert success or rollback without evidence.
