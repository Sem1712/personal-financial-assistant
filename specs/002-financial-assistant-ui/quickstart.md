# Quickstart: Financial Assistant Interface

See the [contract](./contracts/local-ui.md) and [data model](./data-model.md) for precise behavior. Use only synthetic exports for validation.

## Prerequisites

- Python 3.15+, uv, Docker with a running daemon, and a modern local browser.
- A local `.env` configured as in the repository [README](../../README.md), with placeholder passwords replaced locally; never commit credentials or real bank exports.
- Synthetic Intesa-format XLSX fixtures in a local folder accessible to the application. Do not send them to external services.

## Setup and run

From the repository root:

```sh
uv sync --locked
docker compose up -d --wait
uv run --locked alembic upgrade head
uv run --locked personal-financial-assistant serve-ui
```

Open `http://127.0.0.1:8765/` on the same machine. The initial screen is the unavailable-chat placeholder; import and transactions remain reachable. The service must not listen on external interfaces. Stop it with Ctrl+C; a running import whose completion cannot be confirmed must be reported as unknown when the application is reopened.

## End-to-end checks

1. Open Import, enter a synthetic export folder, and start an import. While running, verify the interface blocks navigation and a second start; after completion, verify the counts and unresolved indicator. Repeat to confirm unchanged data. With storage available, try an empty folder and an invalid export; verify distinct no-files and failure states. With storage unavailable, an empty folder must report storage failure rather than no files.
2. Open Transactions and compare rows and details with the synthetic reference. Check date, status, text, bank category, no-recorded-category and signed amount filters individually and combined; clear filters. Confirm conflicting source categories, no linked observations, pending debits, unknown status, and identical-looking occurrences are presented accurately.
3. Verify no-history, no-filter-match and unavailable-database states are distinct. Confirm invalid date and amount ranges produce actionable validation errors.
4. Open a second tab before starting a deliberately delayed import. Verify it detects the run and blocks navigation, then restores navigation after completion. Reload or reopen during the import. If the service remains alive, reattach to its running/result state; if its outcome cannot be established after a restart, report unknown rather than success or failure. After a successful import, verify updated transactions appear without restarting.
5. Verify the local browser makes no external requests, financial values and folder paths do not appear in logs or URLs, and foreign Host/Origin requests are rejected. Use synthetic data for all checks.
6. With a controlled stalled workbook worker, verify the operation deadline, worker termination and reaping, no partial import, and explicit failure or unknown outcome. If worker cleanup cannot be confirmed, verify new imports remain disabled with an explicit error.
7. Interrupt an import-start response and verify a different run cannot be mistaken for that request, including after closing and reopening the tab. Browser storage retains only opaque run IDs; if unavailable, importing is disabled explicitly. Confirm a superseded run's outcome remains visible while a newer running import blocks navigation.
8. For an interrupted request with no recorded run, use **Resolve unrecorded import** after ownership is available. Verify the outcome remains unknown, transactions can be inspected, and no retry is submitted automatically. Confirm a delayed request using that ID cannot start, including after restarting the service.

## Automated validation

Provision the local test browser with `uv run --locked playwright install chromium`;
install Playwright's operating-system library prerequisites if needed. No live model
service is required. Focused UI checks are:

```sh
uv run --locked pytest tests/unit/ui tests/unit/transactions tests/integration/test_ui_imports.py tests/integration/test_transaction_queries.py tests/integration/test_ui_browser_e2e.py tests/integration/test_migrations.py tests/browser
```

Then run the configured gates:

```sh
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pyright
uv run --locked pytest
```

PostgreSQL integration and migration tests require Docker; browser journeys require the provisioned local browser. Report missing prerequisites or skipped required tests as incomplete, not passing. Independently run the five-person usability scenarios and thresholds in the [specification](./spec.md).
