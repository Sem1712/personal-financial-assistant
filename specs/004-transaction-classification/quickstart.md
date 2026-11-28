# Quickstart: Transaction Classification and Context

These are validation instructions for after implementation. Use synthetic data only. Do not place bank exports, notes or credentials in logs or version control.

## Prerequisites

- Python 3.15+ and uv, with project dependencies available from the lockfile.
- Docker with a running daemon; PostgreSQL integration tests use testcontainers.
- A working Playwright browser and system dependencies for browser and browser/PostgreSQL tests.
- For the manual UI smoke check, leave loopback port 8765 free. The planned synthetic demo owns a disposable PostgreSQL container and must never connect to the configured application database.

```sh
uv sync --locked
```

## Targeted verification

After implementation, run the focused existing suites and the new enrichment tests named below; add the planned test files during implementation.

```sh
uv run --locked pytest \
  tests/unit/transactions tests/unit/infrastructure/test_models.py \
  tests/unit/ui/test_transaction_routes.py tests/unit/ui/test_enrichment_detail.py \
  tests/integration/test_enrichment_schema.py \
  tests/integration/test_transaction_queries.py \
  tests/integration/test_transaction_enrichment.py \
  tests/integration/test_enrichment_concurrency.py \
  tests/integration/test_ingestion_reconciliation.py \
  tests/integration/test_migrations.py \
  tests/browser/test_transactions.py tests/browser/test_enrichment_provenance.py \
  tests/browser/test_enrichment_context.py \
  tests/integration/test_ui_browser_e2e.py
```

Expected: synthetic classified and unclassified occurrences retain all independent fields, each source is labeled, context and bank evidence remain separate, invalid multi-field writes roll back, distinct same-looking occurrences stay distinct, repeated imports and pending-to-booked reconciliation preserve enrichment, and concurrent disjoint changes are not lost. Verify fresh and representative pre-feature migration upgrades and a guarded downgrade. Browser checks cover missing values, safe text rendering, no edit controls, detail retry and unchanged list/filter behavior. A missing Docker daemon or browser is a failed or skipped required check, not a pass.

## User-facing validation

After implementation of T030, start the isolated synthetic demo:

```sh
uv run --locked python -m tests.fixtures.enrichment_demo
```

The demo creates and migrates a disposable testcontainers PostgreSQL database, populates synthetic classified and unclassified occurrences, and starts the actual UI on `http://127.0.0.1:8765/`. It overrides any pre-existing `PFA_DATABASE_URL` with the disposable container's URL and never connects to an existing application database. It fails explicitly if the port is occupied. Leave it running while inspecting the interface, then press Ctrl+C to stop the server and remove the disposable container. If startup fails, it must clean up the container.

Open the displayed URL and inspect both transactions. Confirm details show type, category, budget treatment, each status/source/confidence, and separately labeled user and AI explanations. Missing items are explicit; bank suggestions remain separately labeled. No classification or note editing appears, and classifications do not appear in the list. Excluded treatment is explained as intended exclusion from future budgets.

Run the specified task exercise with at least five representative users and record whether at least four correctly distinguish bank suggestions from classification, identify source and uncertainty, and describe excluded treatment. Do not substitute an automated browser test for this user exercise.

## Full quality gates

```sh
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pyright
uv run --locked pytest
```

Report skipped, unavailable or failed required checks. The earlier UI modernization exception is scoped to that feature and does not waive this feature's checks.
