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

Details also show independent transaction type, category, and budget treatment, each
with its status, source, and optional confidence. Bank-suggested categories remain
separate original evidence. User annotations and user/AI explanations appear separately;
missing information is explicit. Excluded treatment indicates intended future budget
exclusion, not a calculated budget. These fields are read-only in the UI: no classifier,
editing interface, or budget calculation is provided.

Other local Python components can use the async `transactions.update_enrichment` boundary
with an `EnrichmentUpdate` patch. Omitted fields are unchanged and null clears a field;
each supplied classification replaces its complete value and provenance. AI and rule
updates may replace even confirmed user classifications. Confidence is an exact decimal
string from 0 to 100 with at most two decimal places. Updates are atomic and preserve
imported observations. If `EnrichmentCommitUnknown` is raised, read the current detail
before retrying. Notes and financial data stay local and must not be logged.
Enrichment validation errors include a safe reason without input values.
Category and context text cannot contain NUL or unpaired Unicode surrogates, which
PostgreSQL cannot store.

Trusted local Python consumers can manage merchants and literal matching entries through
the async `rules` module and call `identify_merchant` for an occurrence. Matching uses
case-folded, whitespace-normalized operation and details fields separately; ambiguous
matches are reported rather than arbitrarily chosen. Merchant identification does not
change the source data or category. The same service boundary supports user-directed
category defaults, preferences and per-occurrence overrides; `evaluate_rules` explicitly
applies them without changing unrelated fields. An override is restored on evaluation
even if the general enrichment boundary changed the category; clearing an override does
not immediately reclassify it. Trusted local consumers can submit AI-origin proposals
and explicitly review protected changes and per-occurrence conflicts. Approvals apply
only to the reviewed pair and revisions, and do not bypass rule precedence; stale
previews must be reviewed again. User-directed operations require an actual user
instruction, not model output. Rule-management controls are not provided in the UI.
Newly imported occurrences are evaluated after the import commits; existing occurrences
are not automatically reclassified on overlapping imports. Each import returns a
correlation ID and an evaluation summary. Incomplete evaluation produces a sanitized
warning without undoing the import.

Use `rules.inspect_work` to inspect durable pending, failed and completed evaluations,
optionally by correlation ID or occurrence IDs. `rules.retry_work` explicitly retries
selected pending or failed items; it checks durable state before retrying an unknown
commit. `rules.reapply_selected` evaluates only the selected occurrences. Both accept
up to 500 distinct occurrence IDs and report individual outcomes. Cancellation during
a commit raises `rules.RulesCommitCancelled`; inspect current state before retrying
because the commit outcome is unknown. A pinned database
connection remains caller-owned and must have no active transaction. Review and
evaluation outcomes are local and may contain sensitive classifications; do not log them.
Outcomes recorded before the explanation migration expose unavailable merchant-decision
and category-conflict details as `None`; they are not reconstructed from current rules.
Merchant rules and review data remain local; downgrading the merchant-rules migration is
refused while its feature data exists.

The category-whitespace migration refuses to upgrade if legacy storage contains a
whitespace-only classification. Correct or clear those classifications locally and retry;
the migration does not silently alter them.

For example, with an existing async engine and occurrence ID:

```python
from personal_financial_assistant.transactions import (
    EnrichmentUpdate,
    update_enrichment,
)

patch = EnrichmentUpdate.model_validate(
    {
        "category": {
            "value": "groceries",
            "status": "provisional",
            "source": "ai",
            "confidence": "72.5",
        },
        "user_annotation": "Weekly shopping",
    }
)
result = await update_enrichment(engine, occurrence_id, patch)
```

The responsive interface uses locally bundled Bootstrap CSS and a custom dark theme,
including native form controls, muted hints, and readable status colors.
Filters sit in a keyboard-operable accordion, collapsed by default. Toggling it
preserves drafts and applied criteria without fetching results. Applied filters
remain visible outside the accordion while draft inputs are edited. Details expand beneath
the selected transaction using a single chevron Details toggle, with Retry available
on failure. Selecting the same toggle collapses it; selecting another opens that row
instead. Recorded operations lead each row; booking and reconciliation status remain
in details. Recorded source details appear as smaller muted text below operations,
kept to one line with an ellipsis if too long; full text remains in expanded details.
Distinct source operations and details are shown without choosing a preferred source.
Amount bounds are inclusive absolute EUR values with a minimum of zero, independent
of the sign. Transaction type selects All, negative Withdrawals, or positive Deposits;
zero is included only in All. Negative bounds are rejected. All criteria combine,
and exact integer/numeric comparison supports the full signed-64-bit magnitude.
Positive amounts have distinct 2px green card borders, except when Deposits is the
applied filter: deposit-only results use neutral borders, including during paging.
Draft selector changes do not affect current borders. EUR expenses of 99.95 or
more (signed amount <= -99.95 EUR) have red borders, compared using exact integer
cents. Other negative and zero amounts retain neutral borders; no currency
conversion is assumed.
Pages contain up to 100 records by default. Centered First/Previous/Next controls
appear above and below the list, with First separated from the Previous/Next pair.
Unavailable controls remain visible with muted text, gray backgrounds, and a
not-allowed cursor.
Top pagination keeps the current position where page height allows. Bottom pagination
scrolls smoothly to the top pagination bar; reduced-motion preferences use an instant
jump instead.
During paging, previous rows stay dimmed and noninteractive until their replacement
is ready, preventing layout collapse. Focus moves to the corresponding top control
without scrolling again. First preserves applied filters.
Placeholders are smaller, lighter, italic hints, with explicit example prefixes,
distinct from entered text. Focus rings mark
form controls and keyboard-focused buttons, not headings or status messages.
Rejected folder submissions remain distinct from earlier completed imports. Date
filters accept canonical years 0001-9999 and identify unsupported values at the field.
Import submission/recovery keeps focus on the visible status when its active control
becomes unavailable, without moving focus from unrelated controls.

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

Database integration tests use testcontainers and require access to Docker.
For this UI modernization only, the maintainer approved playground checks and their
own usability approval instead of required browser suites, formal acceptance matrices,
or participant studies. Required non-browser tests run with:

```sh
uv run --locked pytest --ignore=tests/browser --ignore=tests/integration/test_ui_browser_e2e.py
```

Existing Playwright browser/E2E tests remain optional when a working runner is already
available. No browser or system-package installation is required or authorized:

```sh
uv run --locked pytest tests/unit/ui tests/browser
uv run --locked pytest tests/integration/test_ui_browser_e2e.py
```

Missing browser libraries do not block this feature's UI approval. Optional tests
that have not run are not reported as passing.
See the [UI modernization validation guide](specs/003-modernize-ui-ux/quickstart.md)
for playground examples, PostgreSQL/package checks, and the scoped verification
exception. Other features retain the ordinary project quality gates.

### Bundled styling

Bootstrap **5.3.9** is redistributed under its
[MIT license](src/personal_financial_assistant/ui/static/bootstrap.LICENSE.txt).
The [compiled stylesheet](src/personal_financial_assistant/ui/static/bootstrap.min.css)
comes from [the pinned upstream distribution](https://cdn.jsdelivr.net/npm/bootstrap@5.3.9/dist/css/bootstrap.min.css);
the license comes from [the matching upstream tag](https://raw.githubusercontent.com/twbs/bootstrap/v5.3.9/LICENSE).
No CDN, fonts, Bootstrap JavaScript, component library, or frontend build tool is used
at runtime. Application styles override native select/validation images for the
unchanged local-only CSP and ensure hidden areas stay hidden.

Locally verified asset checksums:

```text
Original CSS SHA-384 (base64):
yEPZ7jP9S0QKiUQ0m3jjsO4ProIW7wvR9gXkI7JOGa2XVsw53Yke2bsdkBbjmmiX
Original CSS SHA-256:
9caac977a0af0c2229abd397eee3345899c4020da2a1a0b711c1cc543fe3719d
Shipped CSS SHA-256:
c9bc71775fc1b123988415e6c828399584f23cc950131d381eaad9e37c075a04
```

Only the final `/*# sourceMappingURL=bootstrap.min.css.map */` line was removed;
copyright and license notices remain intact. To reproduce or update the asset:

1. Download compiled CSS and the full license from an explicit matching upstream tag
   into a fresh temporary directory, not directly over the shipped files.
2. Verify the unmodified download against the upstream integrity value and record
   its SHA-256. For the current version, compare with the original hashes above.
3. Remove only the final source-map line (`sed '$d'` on this version's downloaded CSS),
   preserving all other bytes and notices. Verify the shipped SHA-256 before copying
   the CSS and license into the static directory.
4. For a version change, record the new provenance/hashes here and review the upstream
   release. Run applicable asset/unit/security and installed-wheel checks and inspect
   the playground as described in the validation guide; browser suites are optional
   for this scoped modernization. Retain labels, focus, and validation behavior;
   other features follow their applicable constitutional quality gates.

## Project guidance

The project constitution and engineering rules are in [AGENTS.md](AGENTS.md); the
[constitution entry point](.specify/memory/constitution.md) references that file.
In a Spec Kit-enabled agent session, `/speckit-specify`, `/speckit-plan`,
`/speckit-tasks`, and `/speckit-implement` can be used to take a feature from specification
through implementation.