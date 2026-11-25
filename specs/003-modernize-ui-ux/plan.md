# Implementation Plan: Modernize UI and UX

**Branch**: `003-modernize-ui-ux` | **Date**: 2026-11-24 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/003-modernize-ui-ux/spec.md`

**Status**: Phase 0 research and Phase 1 design complete; implementation not started.

## Summary

Modernize the existing local UI using locally vendored Bootstrap 5.3.9 CSS, a small
application stylesheet, and the current native JavaScript modules. Improve navigation,
forms, status feedback, and transaction readability without changing ingestion,
persistence, API, or financial semantics. Use inline transaction details.

No Bootstrap JavaScript, component library, frontend framework, Node toolchain, or
new Python dependency is needed. Chat remains unavailable and initially selected
unless import recovery requires Import. Playground checks and maintainer approval
validate UI usability. Required browser-suite, formal acceptance-matrix, and study
gates were removed; existing interaction behavior remains required.

## Technical Context

**Language/Version**: Python >=3.15; existing HTML, CSS, and browser-native JavaScript
ES modules. Preserve strict Python typing and document non-obvious JavaScript
presentation shapes where needed without transpilation.

**Primary Dependencies**: Existing FastAPI, Starlette StaticFiles, Uvicorn,
SQLAlchemy async APIs, and ingestion services. New presentation asset: Bootstrap
5.3.9 compiled CSS under its MIT license. Python dependencies and lockfile unchanged.

**Storage**: Existing Docker-hosted local PostgreSQL and Alembic schema, unchanged.
Retain only existing opaque import-request IDs in browser storage. No new filter,
theme, or financial-data persistence.

**Testing**: Existing pytest, pytest-asyncio, pytest-playwright, HTTPX, and
testcontainers. Controlled browser responses cover presentation; real PostgreSQL
integration covers imports and queries. Existing browser fixtures and real-server
E2E code remain optional regression coverage; neither their execution nor browser
provisioning is a gate for this feature.

**Target Platform**: Loopback service at `http://127.0.0.1:8765/`, inspected in the
integrated-browser playground. Responsive layout remains a design requirement,
without an exhaustive width/browser acceptance matrix.

**Project Type**: Local Python application with an embedded static browser UI.

**Performance Goals**: Preserve request deadlines, bounded pagination, import polling,
and stale-response guards. No new per-row network calls or artificial loading delays.
No participant timing thresholds or new backend latency guarantee are required.

**Constraints**: Offline runtime; unchanged CSP, Host/Origin/token checks, cache policy,
and sanitized errors. No external fonts, icons, telemetry, or runtime CDN.
Amounts remain string/BigInt based. Bootstrap must not defeat `hidden`, require
`data:` image allowances, or substitute visual validation for accessible errors.
Playground checks and the maintainer's usability approval are sufficient UI evidence
under the scoped exception in the specification. Non-browser checks remain required.

**Scale/Scope**: One local user, three existing areas and their state variants,
paginated transactions, and linked observations. Playground fixtures:
small controlled fixtures suitable for playground checks; no study dataset minimum.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Authority: [AGENTS.md](../../AGENTS.md), version 1.0.0, through the
[constitution entry point](../../.specify/memory/constitution.md).

| Gate | Pre-research assessment | Post-design assessment |
|------|-------------------------|------------------------|
| Module boundaries | Pass: UI owns presentation; public services and shared engine retained. | Pass: UI assets and related tests/docs only; no private ingestion dependencies. |
| Simplicity | Pass: reuse current modules and one established styling library. | Pass: compiled CSS, native controls, inline details, small overrides; no new framework. |
| Async-first execution | Pass: existing fetch and async Python resources retained. | Pass: no new blocking runtime integration; engine/coordinator ownership, cleanup, deadlines, and concurrency unchanged. |
| Unit/integration coverage | Existing asset/unit and PostgreSQL suites remain required. | Approved scoped exception: browser/E2E coverage is optional; playground checks validate UI behavior. |
| Financial reliability | Pass: no new guidance or calculations. | Pass: exact amounts, occurrence identity, evidence uncertainty, and import recovery semantics preserved. |
| Technology/local data | Pass: uv, Ruff, strict Pyright, async SQLAlchemy, Alembic, Docker PostgreSQL retained. | Pass: locally vendored licensed CSS; no schema, provider, dependency, or security-policy change. |
| Workflow/release gates | Spec defines behavior and failure handling. | Approved scoped exception: playground/maintainer UI approval plus Ruff, strict Pyright, non-browser tests, and package checks. |

The maintainer-approved verification exception is documented in
[spec.md](./spec.md#scoped-verification-exception-approved-2026-11-24), including its
rationale, scope, compatibility, and resolution condition. No global constitutional
amendment is made. These assessments do not fabricate executed test results.

## Project Structure

### Documentation (this feature)

```text
specs/003-modernize-ui-ux/
  spec.md
  plan.md
  research.md
  data-model.md
  quickstart.md
  checklists/requirements.md
  contracts/ui-presentation.md
```

`tasks.md` is a later `/speckit-tasks` output, not created here.

### Source Code (repository root)

```text
src/personal_financial_assistant/ui/
  app.py                         # Existing static serving, normally unchanged
  security.py                    # Existing policy, unchanged
  static/
    index.html                   # Semantic shell, grouped forms, status regions
    styles.css                   # Theme, responsive rows, accessible overrides
    bootstrap.min.css            # New pinned compiled CSS
    bootstrap.LICENSE.txt        # New upstream license
    app.js                       # Selected navigation and view-change focus
    chat.js                      # Existing placeholder links
    import.js                    # Explicit status and field feedback
    transactions.js              # Rows, filter summary, inline details
tests/
  browser/
    conftest.py                  # Existing optional browser fixture
    test_navigation.py
    test_import.py
    test_transactions.py
  unit/ui/test_app.py             # Asset-serving checks
  integration/test_ui_browser_e2e.py
README.md                        # Local assets, attribution, update procedure
```

**Structure Decision**: Keep the embedded static application, not a separate
frontend project. Vendor at the static root so existing fake servers' basename-based
asset routing remains compatible. Extend current test files and runner. Confirm
wheel inclusion of CSS and license; source-checkout serving alone does not prove
installed-package behavior.

## Phase 0: Research Decisions

See [research.md](./research.md) for decisions, alternatives, and verified upstream
references. All unknowns are resolved: Bootstrap 5.3.9 CSS only, no component library,
small contrast/CSP-aware overrides, native controls, responsive occurrence rows,
inline details, unchanged APIs/state, and playground-based UI verification.

## Phase 1: Design and Verification

### Ownership and interfaces

- `index.html` defines stable view roots, labels, headings, live status regions,
  applied-filter summary, and detail region. Retain IDs and accessible action names
  where practical; do not simulate unavailable features.
- `styles.css` owns theme variables, wrapping, focus, contrast-correct semantic
  treatments, responsive rows, and Bootstrap compatibility overrides. Bootstrap
  supplies actual grid and control styling rather than an unused stylesheet.
- `app.js` remains the navigation owner. Update selection and `aria-current` only
  after successful navigation. Focus a destination heading on a real view change,
  not during same-view import polls. Enumerate known view roots so nested sections
  are not inadvertently toggled as application views.
- `import.js` retains correlation, polling, storage, locks, and recovery. Add explicit
  presentation kinds alongside existing messages; do not classify states by parsing
  message strings. Preserve validation across polls and avoid identical announcements.
- `transactions.js` retains filters, cursors, generation guards, and exact amount
  handling. Applied-filter summaries describe the validated query, not editable drafts.
  Detail selection uses opaque occurrence IDs, not visible date/amount as identity.
  Continue rendering bank data as text.
- No payloads, database entities, migrations, coordinator ownership, model provider,
  or runtime-resource lifecycles change.

### Assets and operations

Vendor official compiled CSS and full MIT license with copyright header intact.
Verify the downloaded CSS against the official SHA-384 in
[research.md](./research.md). Record provenance, checksum, and any deterministic
removal of the optional source-map trailer in README. Commit packaged assets during
implementation; never download them at application startup or installation.
Load Bootstrap before application CSS through same-origin links. No Sass build.

### Data and contracts

See [data-model.md](./data-model.md) for transient presentation states and unchanged
record relationships, and [ui-presentation.md](./contracts/ui-presentation.md) for
DOM, navigation, status, filter, detail, and HTTP compatibility contracts.

### Verification and release

Follow [quickstart.md](./quickstart.md). Inspect changed UI behavior in the playground:
selected navigation/focus, responsive controls/rows, explicit status kinds, field
associations, applied-versus-draft summaries, detail identity/close/retry, stable
announcements, and CSP-compatible local assets. Keep required asset/security and
non-browser contract tests. Existing browser tests for duplicate starts, recovery,
safe rendering, exact amounts, and query semantics remain optional regression coverage.

Use playground checks for changed UI behavior; existing browser tests are optional.
Before merge run Ruff, strict Pyright, non-browser unit/integration tests, and package
checks. PostgreSQL tests still require Docker. Browser libraries, E2E port availability,
participant recruitment, and exhaustive acceptance matrices are not feature gates.

## Complexity Tracking

No constitutional violations or additional architectural layers.
