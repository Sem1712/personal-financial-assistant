# Personal Financial Assistant Constitution

## Core Principles

### I. Explicit Module Boundaries and Shared Resources

Every module MUST have one documented responsibility and a defined public interface.
Transaction ingestion, financial analytics, decision support, and infrastructure MUST have
distinct scopes. Modules MUST NOT depend on another module's private implementation.
Resources used across modules, including database access, model API clients, and configuration,
MUST be provided through focused shared modules rather than duplicated implementations.
Shared modules MUST remain domain-neutral and MUST NOT become containers for unrelated logic.
This keeps responsibilities independently understandable and testable.

### II. Maintainability and Simplicity

Changes MUST use the simplest design that satisfies the specified behavior. Code MUST use
clear names, explicit types, small cohesive functions, and existing project conventions.
New abstractions and dependencies MUST have a concrete current use case; speculative
generality is not acceptable. Public interfaces and non-obvious operational requirements
MUST be documented, and directly affected documentation MUST change with behavior.
Errors MUST be surfaced explicitly rather than hidden by broad exception handlers,
silent defaults, or success-shaped fallbacks.

### III. Async-First Execution

Runtime workflows MUST use asyncio end to end for I/O, including database operations,
model API calls, and ingestion. Async call paths MUST NOT perform blocking I/O on the
event loop. Unavoidable synchronous integrations MUST be isolated and explicitly
offloaded; pure computation does not require artificial async wrappers.
Resource ownership, cleanup, cancellation, and I/O timeouts MUST be explicit.
Concurrency MUST be bounded where it consumes external or shared resources.
Synchronous tooling and migration commands are outside the runtime async requirement.

### IV. Unit and Integration Test Coverage

All application modules MUST have pytest unit tests covering their observable behavior,
including meaningful edge cases and error paths. New or changed behavior MUST include
focused tests that fail without the implementation or fix. Unit tests MUST isolate
external services and remain deterministic.

Integration tests MUST cover module contracts, PostgreSQL persistence and transactions,
schema migrations, and model API request/response handling. Database integration tests
MUST use testcontainers with real PostgreSQL rather than SQLite substitutes.
Async behavior MUST be exercised with asyncio-compatible pytest support.
Model API integration tests MUST use controlled responses; live LM Studio smoke tests
MUST be separately identified and MUST NOT determine ordinary test-suite reliability.

### V. Reliable and Explainable Financial Guidance

Financial calculations MUST use exact decimal or integer minor-unit representations,
with explicit currency and rounding rules; binary floating point MUST NOT determine
monetary results. Ingestion MUST validate inputs and prevent duplicate transactions on
reprocessing. Analytics and recommendations MUST distinguish recorded facts,
deterministic calculations, assumptions, and model-generated interpretations.

Financial-responsibility assessments and purchase guidance MUST explain the evidence and
limitations behind their conclusions. Direct-payment and installment comparisons MUST
disclose the available cost, interest, fee, and repayment assumptions. Missing or stale
inputs and unavailable or invalid model responses MUST be reported explicitly, not
converted into confident affordability judgments. Guidance is advisory and MUST NOT
execute purchases, transfers, or credit commitments.

## Technology and Data Constraints

- Python packaging, dependencies, lockfiles, and execution MUST be managed with uv.
- Ruff MUST provide linting and formatting. Pyright MUST run in strict mode.
- SQLAlchemy's async APIs MUST provide database access through shared infrastructure.
  Alembic MUST manage versioned schema migrations; runtime table creation is not a
  substitute for migrations.
- Persistent application data MUST reside in a locally hosted PostgreSQL database
  running in Docker. Database schema changes MUST include reviewed Alembic migrations.
- LM Studio local APIs MUST be the initial provider for model inference and
  decision-support calls. Model-specific behavior MUST remain behind a defined client
  boundary. Any provider change MUST be explicitly reviewed against this constitution.
- asyncio, pytest, and testcontainers MUST be the runtime and testing foundations
  described in the core principles.
- Bank data and model prompts containing financial data MUST remain within the local
  system. Credentials MUST NOT be committed, and logs MUST NOT expose credentials or
  raw sensitive financial payloads. Connection settings MUST be external configuration.

## Development Workflow and Quality Gates

Feature specifications MUST define inputs, outputs, acceptance criteria, and failure
behavior before implementation. Plans MUST identify module ownership, shared-resource
boundaries, async execution, data changes, and unit/integration verification.

Before merge, changes MUST pass Ruff linting and formatting checks, strict Pyright
checking, and the applicable pytest unit and integration suites, all executed through uv.
Full configured quality gates MUST pass for the release candidate. Failed or skipped
required checks MUST be reported; a missing database or model service MUST NOT be
treated as a passing integration check.

Reviews MUST verify constitutional compliance, test evidence, maintainability, financial
calculation correctness, and directly affected documentation. Migration changes MUST be
tested against both an empty database and an existing supported schema with representative
data. Model-dependent tests MUST assert contracts and validation behavior rather than
uncontrolled generated wording.

## Governance

This constitution is the authoritative source of project engineering rules. Specifications,
plans, tasks, implementations, and reviews MUST comply with it. Conflicts MUST be resolved
explicitly before the affected implementation proceeds.

Amendments MUST document the proposed change, rationale, compatibility impact, and any
required migration or follow-up work. The project maintainer MUST approve an amendment
before it takes effect. The constitution version and amendment date MUST be updated
with each approved change; the original ratification date MUST be preserved.

Versioning MUST follow semantic rules: MAJOR for incompatible principle removals or
redefinitions, MINOR for new principles or materially expanded guidance, and PATCH for
non-semantic clarifications and corrections. Every specification/plan review and change
review MUST check compliance. Exceptions MUST be explicit, maintainer-approved, scoped
to the affected work, and accompanied by a rationale and a resolution condition.

**Version**: 1.0.0 | **Ratified**: 2026-11-22 | **Last Amended**: 2026-11-22
