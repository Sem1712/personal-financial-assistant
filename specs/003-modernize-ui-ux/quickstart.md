# Quickstart Validation: Modernize UI and UX

This guide describes playground validation and retained engineering checks.
See [presentation contract](./contracts/ui-presentation.md) and
[data model](./data-model.md). Use synthetic information only.

## Prerequisites

- Python >=3.15 and uv; existing project dependencies.
- Docker with a running daemon for real PostgreSQL integration.
- The integrated-browser playground for UI checks. No browser runner or system-library
  installation is required or authorized.
- Existing local configuration as described in [README](../../README.md).
  Never commit credentials or use real financial exports for validation.
- A free loopback port 8765 when running the UI. Do not terminate another process
  to free it. Real-server browser E2E is optional, not a feature gate.
- Bootstrap CSS and license already vendored during implementation; no runtime download.

## Setup and run

From the repository root:

```sh
uv sync --locked
docker compose up -d --wait
uv run --locked alembic upgrade head
uv run --locked personal-financial-assistant serve-ui
```

Open `http://127.0.0.1:8765/` in the local browser. Stop the manual UI with Ctrl+C before
running tests that need port 8765. Do not create a second server on the occupied port.

No migration is introduced by this feature; the upgrade command prepares the existing
schema. For manual fixtures, use the existing synthetic workbook helper or prepared
synthetic exports from the [previous UI validation guide](../002-financial-assistant-ui/quickstart.md).
Small controlled fixtures are sufficient for playground checks. No participant
study, minimum dataset size, or formal pagination acceptance matrix is required.

## Focused automated checks

Required non-browser checks:

```sh
uv run --locked pytest tests/unit/ui
uv run --locked pytest tests/integration/test_ui_imports.py tests/integration/test_transaction_queries.py
```

Use controlled playground responses for changed UI behavior. ASGI asset/security
tests verify actual headers; mocked playground responses do not prove CSP compatibility.
Existing browser/E2E tests remain optional regression coverage when a working runner
is already available.

Do not install new runners, browser/system packages, or Python dependencies for this
redesign. Missing browser libraries do not block the approved UI validation scope.

## Package validation

```sh
uv build
```

Inspect the resulting wheel with a ZIP viewer and verify it contains the HTML,
JavaScript, application stylesheet, pinned Bootstrap stylesheet, and full license
under the application static directory. Verify installed-package serving in a clean
local environment without fetching assets. Record original upstream hash verification,
shipped hash, license preservation, and any source-map-trailer removal.

## Playground examples (not a formal acceptance matrix)

Use relevant examples below to inspect changed behavior and confirm usability with
the maintainer. Exhaustive scenario/width execution, timing studies, and formal
accessibility/browser certification are not required.

| Area | Scenario | Required outcome |
|------|----------|------------------|
| Navigation | Normal start; all areas; blocked/recovered import | Correct visible/current area; unavailable Chat/reports; truthful lock reason |
| Keyboard | Skip link, forms, navigation, details, recovery | Logical order; visible focus; no focus inside hidden content or same-view poll focus theft |
| Import | Starting/running, success, repeat, unresolved counts | No duplicate start or fake percentage; all counts and uncertainty readable |
| Import | Blank/invalid folder, empty folder, storage failure | Retained input and associated validation; no-files distinct from failure |
| Recovery | Reload, unknown, multiple outcomes, resolve/dismiss | Existing correlation/locks preserved; each recovered outcome clear; no fabricated success |
| Filters | Combined criteria, drafts, invalid ranges, clear | Correct matches and applied summary; draft edits do not relabel results; invalid entries issue no search |
| Transactions | Negative/zero/large amounts, identical-looking occurrences | Exact signed values/currency; no merged occurrences |
| Evidence | Pending credits/debits, unknown/unresolved, conflicting/missing source | Existing meanings and bank-suggestion labels preserved |
| Details | Open, close, retry failure, rapid selection/page changes | Correct selected ID/context, safe wrapped text, focus return, no stale replacement |
| Empty/error | No history, no matches, list/category/detail failure | Distinct messages and applicable import/clear/retry actions |
| Layout | Long paths/text, all widths | No clipped/overlapping actions or page-level horizontal scrolling |
| Privacy | External destinations blocked; loopback allowed | Zero external requests, no missing required assets or CSP violations, no sensitive URLs/logs |

Inspect playground behavior and console when useful. Bootstrap select/validation
images must not attempt blocked data-URL loads. Status styling must not defeat `hidden`.
For optional offline inspection, do not enable a global browser offline switch that also disables
the required loopback service; block external destinations specifically.

## UI approval and scoped exception

Playground checks and the maintainer's own usability approval are sufficient for
this feature. The maintainer has confirmed the current UI is usable. Keep existing
labels, focus, truthful states, exact values, and local-data behavior; verify future
UI corrections in the playground. No participant recruitment, timing thresholds,
ratings survey, or required browser-suite execution is needed.

The [approved constitutional exception](./spec.md#scoped-verification-exception-approved-2026-11-24)
applies only to this UI modernization and is reviewed if the audience expands or
the maintainer reinstates browser gates. It does not waive non-browser integration
tests or financial/security requirements. Waived tests are not passing tests.

## Final configured gates

```sh
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pyright
uv run --locked pytest --ignore=tests/browser --ignore=tests/integration/test_ui_browser_e2e.py
```

The required non-browser suite includes migration checks on real PostgreSQL; no migration
change is introduced here. No LM Studio service is needed. Missing Docker or failed
required engineering checks remain incomplete. Browser libraries, browser/E2E
execution, and participant availability are not blockers for this feature.
