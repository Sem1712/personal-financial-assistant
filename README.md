# Personal Financial Assistant

A planned local-first assistant for understanding bank transactions, assessing financial
responsibility, and exploring whether to make a purchase outright or in installments.

**Status:** This repository currently contains a uv project and a placeholder CLI that prints
a greeting. Transaction ingestion, analytics, purchase guidance, the database, model integration,
tests, and quality tools are not implemented or configured yet.

## Planned workflow

1. Ingest bank transactions, validate and normalize them, and prevent duplicate imports.
   The bank connection and input formats are yet to be defined.
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

Only the Python/uv project scaffold exists today. The other integrations and tools above are
the intended stack, not installed project dependencies.

## Getting started

Install [uv](https://docs.astral.sh/uv/) and make Python 3.15 or newer available to it. uv can
also install a managed Python interpreter when needed.

```sh
# Create and synchronize the project environment from the lockfile.
uv sync --locked

# Run the current placeholder CLI.
uv run --locked personal-financial-assistant
```

The CLI currently prints `Hello from personal-financial-assistant!`.

The planned database and integration tests will also require Docker with a running daemon.
Model-assisted features will require LM Studio with a model loaded and its local API server
running.

## Planned development commands

These commands are not usable as project quality gates yet. They require the corresponding
dependencies, configuration, and tests to be added first:

```sh
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
```

Database integration tests are intended to use testcontainers and require a running Docker
daemon. Once a Docker Compose configuration and Alembic migrations exist, the intended
database startup and migration commands are:

```sh
docker compose up -d
uv run alembic upgrade head
```

## Project guidance

The project constitution and engineering rules are in [AGENTS.md](AGENTS.md); the
[constitution entry point](.specify/memory/constitution.md) references that file.
In a Spec Kit-enabled agent session, `/speckit-specify`, `/speckit-plan`,
`/speckit-tasks`, and `/speckit-implement` can be used to take a feature from specification
through implementation.