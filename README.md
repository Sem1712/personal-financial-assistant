# Personal Financial Assistant

A planned local-first assistant for understanding bank transactions, assessing financial
responsibility, and exploring whether to make a purchase outright or in installments.

**Status:** On-demand Intesa Sanpaolo XLSX ingestion and local transaction browsing are
available. Chat, reports, analytics, purchase guidance, and model integration are not implemented.

## Planned workflow

1. Manually download Intesa XLSX exports and import them on demand.
2. Store the data in a locally hosted PostgreSQL database running in Docker. Use asynchronous
   SQLAlchemy for database access and Alembic for schema migrations.
3. Analyze available income, spending, and transaction trends using exact monetary calculations.
4. Use LM Studio's local model API alongside those calculations to provide an explainable
   assessment of financial responsibility, distinguishing facts from model interpretation.
5. Evaluate a proposed purchase and compare paying directly with available installment terms,
   explaining costs, assumptions, and any missing or stale information.

The guidance is intended to be advisory: the application will not make purchases, transfers,
or credit commitments. Financial data and model prompts containing it are intended to remain local.

## Technology

- Python 3.15 or newer, managed with uv; `.python-version` selects Python 3.15.
- asyncio for application I/O.
- Docker-hosted PostgreSQL, async SQLAlchemy, and Alembic for storage and migrations.
- LM Studio local APIs for model-assisted assessment and decision support.
- Ruff for linting and formatting, Pyright in strict mode for type checking, and pytest with
  testcontainers for unit and integration testing.

Database, ingestion, and testing dependencies are installed; model integration remains planned.

## Getting started

Install [uv](https://docs.astral.sh/uv/) and make Python 3.15 or newer available to it. uv can
also install a managed Python interpreter when needed.

```sh
# Create and synchronize the project environment from the lockfile.
uv sync --locked

# Copy .env.example to .env and replace both password placeholders with the same
# local password. URL-encode special characters in the database URL password.
docker compose up -d --wait
uv run --locked alembic upgrade head

# Read all XLSX exports directly in this folder.
uv run --locked personal-financial-assistant ingest-xlsx --input-dir /path/to/exports

# Or start the local browser interface.
uv run --locked personal-financial-assistant serve-ui
```

Open `http://127.0.0.1:8765/` on the same machine. Chat and reports are placeholders;
use Import to enter a local folder and Transactions to browse and filter recorded
occurrences. Transaction details show linked source observations and bank-suggested
categories; conflicting or missing evidence is not resolved by the UI. Export data
does not represent a live balance or guarantee complete history.

The UI blocks in-app navigation while an import may be running. If an outcome cannot
be established after interruption, it is shown as unknown; inspect transactions before
intentionally retrying. If a request has no recorded run, **Resolve unrecorded import**
prevents that request from starting later and preserves its unknown outcome. Multiple
recovered outcomes remain visible until dismissed. Requests, data, and static assets
remain local, and paths and financial filters are not included in URLs. Use the interface
only on a trusted local machine; other software running as the same user may access local data.

Keep bank exports local and outside version control. `PFA_DATABASE_URL` must point to a
loopback PostgreSQL address. `.env` is read from the current directory; environment variables
override it. Never commit credentials or bank files.

The command reads direct, regular `.xlsx` files for one account, ignores temporary and
symlinked files, and reports counts without transaction values. Empty folders are a no-op;
invalid files or storage errors fail the whole batch. Pending and booked states and original
bank categories are retained; categories are suggestions, not classifications. CSV, other
banks, automatic bank connections, and scheduled imports are not supported.
Blank rows and trailing single-cell notes beginning `Nota:`, `Note:`, `Legenda:`, or
`Avvertenza:` in the date or operation column are recognized as footer text; other
incomplete rows fail.
Empty exports are tracked by digest; an identifiable `Conti e Carte:` header is checked
against the selected account, while an absent account is not invented.
Nonempty operation, details, and category cells must be text; other types fail validation
instead of being discarded. Formulas in transaction columns are not supported.

Repeated identical files are skipped. The account/date/signed amount/currency key is a
candidate group, not a unique transaction ID: same-key rows coexisting in a file are retained,
and overlapping exports use the maximum observed per-file count. Distinct identical-key
transactions that never coexist in one export may be undercounted. Ambiguous associations
are reported as unresolved; pending transactions are not automatically cancelled or matched
across changed keys. Newly inferred ambiguous occurrences have unknown booking status, while
the source observations retain their reported statuses. These records describe the supplied
exports, not a live bank balance.

The database and integration tests require Docker with a running daemon.
Model-assisted features will require LM Studio with a model loaded and its local API server
running.

## Development commands

```sh
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pyright
uv run --locked pytest
```

Database integration tests use testcontainers and require access to Docker. Browser
tests use Playwright's local Chromium; provision it with
`uv run --locked playwright install chromium` and install the operating-system
libraries required by Playwright if they are missing. No model service is needed for
the current UI tests. See the [UI quickstart](specs/002-financial-assistant-ui/quickstart.md)
for synthetic scenarios and release checks.

## Project guidance

The project constitution and engineering rules are in [AGENTS.md](AGENTS.md); the
[constitution entry point](.specify/memory/constitution.md) references that file.
In a Spec Kit-enabled agent session, `/speckit-specify`, `/speckit-plan`,
`/speckit-tasks`, and `/speckit-implement` can be used to take a feature from specification
through implementation.