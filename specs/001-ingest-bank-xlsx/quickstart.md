# Quickstart: Validate On-Demand XLSX Ingestion

## Prerequisites

- Python 3.15 and `uv`.
- Docker running locally for PostgreSQL integration tests.
- A local PostgreSQL connection configured in an untracked UTF-8 `.env` in the invocation's working directory. Set `PFA_DATABASE_URL` to the local async PostgreSQL connection URL; never commit real credentials. Process environment overrides `.env`.
- Synthetic workbook fixtures matching the documented Intesa XLSX layout. Do not commit or share the user's actual account export.

## Set up the local database

Copy `.env.example` to `.env`, replace both password placeholders with the same local
password, and URL-encode special characters in the URL password. Then run:

```sh
uv sync --locked
docker compose up -d --wait
uv run alembic upgrade head
```

Expected: PostgreSQL is healthy and the Alembic schema is at head. Missing Docker/database is a blocked integration prerequisite, not a passing test result.
If port 5432 is already in use, use a Compose override with an available loopback host
port and set `PFA_DATABASE_URL` to that port instead; do not stop an unrelated service.

## Run focused validation

```sh
uv run pytest tests/unit
uv run pytest tests/integration
```

Expected: unit tests cover workbook parsing and identity reconciliation; integration tests cover a real PostgreSQL batch, rollback on invalid input, and migrations from empty and representative prior schemas.

Configuration tests must also cover Pydantic CLI parameter validation, `.env` loading, process-environment precedence, missing/invalid required settings, and redacted errors. There are no duration or throughput acceptance thresholds.

## Exercise an import

Place one or more synthetic XLSX fixtures for one selected account in a dedicated local folder, then run:

```sh
uv run personal-financial-assistant ingest-xlsx --input-dir /path/to/bank-exports
```

Expected:

- The command reads every eligible `.xlsx` directly in the folder.
- It reports non-sensitive file/row/transaction counts and any unresolved reconciliation count.
- A second run over the same files adds no transactions and reports unchanged files.
- A malformed eligible file causes a nonzero result and no partial database changes.
- No account or transaction values are printed or sent to external services.

Same-key transactions are only distinguishable when they coexist in an export. The
maximum-multiplicity heuristic can undercount otherwise; ambiguous associations remain
unresolved and must not be interpreted as confirmed matches. A newly inferred
ambiguous occurrence has unknown booking status, while the original observations retain
their reported statuses. Empty exports are tracked without inventing an account; an
identifiable `Conti e Carte:` header is checked against the selected account.

Refer to [the CLI contract](./contracts/cli.md) and [the data model](./data-model.md) for precise import and reconciliation behavior.
