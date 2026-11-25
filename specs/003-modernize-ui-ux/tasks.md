---
description: "Executable tasks for the local UI and UX modernization"
---

# Tasks: Modernize UI and UX

**Input**: Design documents from `specs/003-modernize-ui-ux/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md),
[research.md](./research.md), [data-model.md](./data-model.md),
[presentation contract](./contracts/ui-presentation.md), [quickstart.md](./quickstart.md)

**Verification**: Playground checks and maintainer usability approval are sufficient
for UI behavior under the [approved scoped exception](./spec.md#scoped-verification-exception-approved-2026-11-24).
Ruff, strict Pyright, non-browser unit/PostgreSQL tests, and package checks remain
required. Existing browser/E2E code is optional; no browser installation, formal
acceptance matrix, or participant study is required.

**Organization**: Three independently testable P1 stories, with shared setup and
presentation foundations. No new backend, schema, financial calculations, or provider.

## Format: `[ID] [P?] [Story] Description`

- Every task begins with an unchecked checkbox and a unique sequential ID.
- `[P]` means a task can run alongside its identified different-file peer after
  all listed prerequisites are complete; it does not authorize ignoring dependencies.
- `[US1]`, `[US2]`, and `[US3]` identify the specification's user stories.
- All implementation paths below are relative to the repository root.
- Field citations use the exact human-readable `Entity.field` labels defined in
  [data-model.md](./data-model.md); they describe transient state, not new persisted models.

## Path Conventions

Use the existing `src/personal_financial_assistant/ui/static/`, `tests/browser/`,
`tests/unit/ui/`, and `tests/integration/` layout. Use uv for Python commands.
Do not create a frontend project, a new runner, or speculative shared infrastructure.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Supply the pinned styling asset.

- [X] T001 [P] Vendor official Bootstrap 5.3.9 compiled CSS into `src/personal_financial_assistant/ui/static/bootstrap.min.css` and its full MIT license into `src/personal_financial_assistant/ui/static/bootstrap.LICENSE.txt`; verify upstream SHA-384 from `specs/003-modernize-ui-ux/research.md` locally before any optional source-map-trailer removal, retain copyright notices, and retain original/shipped checksums for T026.

**Checkpoint**: CSS/license are local files.
These tasks do not require dependency-manifest changes or runtime downloads.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish shared styling, asset compatibility, and a verified shell baseline.

All stories depend on this phase's checkpoint; do not add backend foundations.

- [X] T003 [P] Add focused async asset/shell tests in `tests/unit/ui/test_app.py` for local Bootstrap-before-application stylesheet links, successful stylesheet/license serving, and preservation of actual cache/CSP headers; use the existing ASGI client and ensure the new stylesheet-link assertion fails before T005.
- [X] T004 [P] Establish Bootstrap-compatible light-theme variables, common buttons/forms/status surfaces, visible focus and wrapping in `src/personal_financial_assistant/ui/static/styles.css`; add final hidden-state precedence and native select/validation-image overrides from `specs/003-modernize-ui-ux/research.md`, without adding inline styles or relaxing CSP.
- [X] T005 Load `/static/bootstrap.min.css` before `/static/styles.css` in `src/personal_financial_assistant/ui/static/index.html`, preserving module bootstrap, token metadata, existing view/control IDs, and unavailable-feature behavior.
- [X] T006 Run `uv run --locked pytest tests/unit/ui/test_app.py` and check the local CSS/license delivery in `src/personal_financial_assistant/ui/static/`; resolve foundation-caused failures before opening the story phases.

**Checkpoint**: Local library loading and compatibility rules work; existing
business behavior is unchanged. Inspect responsive/interaction behavior in the
playground without formal browser or accessibility certification gates.

---

## Phase 3: User Story 1 - Navigate a clear, consistent application (Priority: P1)

**Goal**: A cohesive shell with truthful selected navigation, reachable available
tasks, unavailable Chat/reports, and keyboard orientation.

**Playground check**: Open the application, navigate areas with pointer and
keyboard, inspect selected navigation/focus, and exercise a
blocked/recovered import without implementing new import or transaction behavior.

### Implementation for User Story 1

- [X] T008 [US1] Modernize the header, main landmark, skip link, navigation buttons, focusable area headings, and Chat placeholder in `src/personal_financial_assistant/ui/static/index.html`; preserve existing accessible action names and three known view roots.
- [X] T009 [P] [US1] Update successful-view rendering in `src/personal_financial_assistant/ui/static/app.js` to enumerate known roots, synchronize selection and focus only on real changes, and retain navigation guards; implement/preserve [Application area.selected area](./data-model.md#application-area), [Application area.navigation-locked flag](./data-model.md#application-area), and [Application area.visible explanatory status](./data-model.md#application-area).
- [X] T010 [P] [US1] Complete shell/navigation/placeholder styling in `src/personal_financial_assistant/ui/static/styles.css` using the shared theme and Bootstrap utilities, including selected and focus states, narrow wrapping, and visibly unavailable capabilities.
**Checkpoint**: US1 is a demonstrable MVP; existing Import and Transactions remain usable.

---

## Phase 4: User Story 2 - Import exports with understandable feedback (Priority: P1)

**Goal**: Readable folder submission, truthful progress/results, field-associated
validation, and understandable existing recovery controls.

**Playground check**: Use controlled imports for running, success/repeat, no-files,
validation/storage failure, unknown, and multiple recovered outcomes; compare labels,
counts, warnings, available actions, and locking with the existing import contract.

### Implementation for User Story 2

- [X] T013 [US2] Group the folder field/help, primary submission, status, labeled counts, and separate recovery actions in `src/personal_financial_assistant/ui/static/index.html`; provide persistent field-feedback and live-status targets without renaming IDs or hiding recovery explanations.
- [X] T014 [P] [US2] Add structured status-kind and stable-announcement rendering in `src/personal_financial_assistant/ui/static/import.js`; follow [Import presentation.presentation kind](./data-model.md#import-presentation), [Import presentation.visible status message](./data-model.md#import-presentation), [Import presentation.existing counts](./data-model.md#import-presentation), [Import presentation.recovered-outcome list](./data-model.md#import-presentation), and [Import presentation.enabled/hidden recovery actions](./data-model.md#import-presentation). Preserve the cited inputs [Import presentation.current/tracked runs](./data-model.md#import-presentation), [Import presentation.current run.state](./data-model.md#import-presentation), [Import presentation.request correlation](./data-model.md#import-presentation), [Import presentation.pending/completed/missing IDs](./data-model.md#import-presentation), [Import presentation.storage availability](./data-model.md#import-presentation), and [Import presentation.start/conflict flags](./data-model.md#import-presentation), without changing the request/poll/recovery algorithms.
- [X] T015 [P] [US2] Style the grouped import form, all count labels, per-run recovered outcomes, uncertainty warnings, and secondary recovery actions in `src/personal_financial_assistant/ui/static/styles.css`, using wrapping and textual distinctions at narrow widths rather than color-only status.
- [X] T016 [US2] Associate folder validation with the retained input in `src/personal_financial_assistant/ui/static/import.js`; implement [Import presentation.input-error association](./data-model.md#import-presentation) and preserve [Import presentation.persistent safe notice](./data-model.md#import-presentation), clearing only applicable invalid feedback without erasing independent recovery notices.
**Checkpoint**: US2 works without a new import lifecycle and remains independently testable.

---

## Phase 5: User Story 3 - Browse and filter readable transactions (Priority: P1)

**Goal**: Scannable occurrences, honest applied filters, readable evidence, and
identity-aware inline detail loading/close/retry behavior.

**Playground check**: With controlled synthetic pages and observations, apply and
edit filters, page results, select duplicate-looking occurrences, inspect/close/retry
details, and distinguish empty/error/loading states at wide and narrow widths.

### Implementation for User Story 3

- [X] T019 [US3] Group filter inputs and Apply/Clear actions, add the applied-filter summary and persistent field-feedback targets, and define an inline detail heading/content/Close/Retry region in `src/personal_financial_assistant/ui/static/index.html`; retain existing IDs, labels, pagination controls, and export-history limitation.
- [X] T020 [P] [US3] Implement applied-summary, field-error association, and explicit query/category feedback in `src/personal_financial_assistant/ui/static/transactions.js` according to [Transaction browsing context.Draft values](./data-model.md#transaction-browsing-context), [Transaction browsing context.Applied filters](./data-model.md#transaction-browsing-context), [Transaction browsing context.Query state](./data-model.md#transaction-browsing-context), [Transaction browsing context.Category state](./data-model.md#transaction-browsing-context), and [Transaction browsing context.Validation association](./data-model.md#transaction-browsing-context); preserve existing filter/parser/request semantics.
- [X] T021 [P] [US3] Style filter groups, one responsive occurrence article layout, applied summaries, pagination, and long inline source text in `src/personal_financial_assistant/ui/static/styles.css`; keep exact values readable at all target widths without duplicated desktop/mobile controls.
- [X] T022 [US3] Render consistent labeled occurrence rows and detail actions in `src/personal_financial_assistant/ui/static/transactions.js`, preserving exact signed amount/currency, source uncertainty, and occurrence identity; preserve [Transaction browsing context.Cursor state](./data-model.md#transaction-browsing-context) and [Transaction browsing context.Response generation](./data-model.md#transaction-browsing-context) while wiring rows to the current applied query.
- [X] T023 [US3] Implement stable inline detail heading/context, safe observation rendering, Close/Retry, focus return, and invalidation on superseding actions in `src/personal_financial_assistant/ui/static/transactions.js`; follow [Selected transaction details.opaque occurrence ID](./data-model.md#selected-transaction-details), [Selected transaction details.date](./data-model.md#selected-transaction-details), [Selected transaction details.exact amount string](./data-model.md#selected-transaction-details), [Selected transaction details.currency](./data-model.md#selected-transaction-details), [Selected transaction details.request state](./data-model.md#selected-transaction-details), [Selected transaction details.linked observations](./data-model.md#selected-transaction-details), and [Selected transaction details.initiating control reference](./data-model.md#selected-transaction-details).
**Checkpoint**: The stories are usable in the playground; browser tests are optional.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Preserve packaged delivery and non-browser engineering checks.
Playground/maintainer approval replaces formal UI acceptance gates.

- [X] T026 [P] Update `README.md` with local Bootstrap version/license/provenance, locally verified original/shipped checksums and any trailer removal, reproducible asset-update procedure, optional browser test commands, required non-browser checks, and the `specs/003-modernize-ui-ux/quickstart.md` guide; do not claim unexecuted tests passed.
- [X] T027 Run `uv build`, inspect CSS/HTML/JS/license inclusion for the package configured in `pyproject.toml`, and verify `src/personal_financial_assistant/ui/app.py` serves those assets from a clean installed-wheel environment without source-checkout fallback or asset downloads; record results in `specs/003-modernize-ui-ux/tasks.md` and remove only task-owned temporary environments/artifacts.
- [X] T030 After T040, run uv Ruff lint/format, strict Pyright, and `uv run --locked pytest --ignore=tests/browser --ignore=tests/integration/test_ui_browser_e2e.py`, including applicable real-PostgreSQL migration/import/query tests. Rebuild and verify changed packaged assets as in T027, preserve API/financial/security contracts, and record actual results in `specs/003-modernize-ui-ux/tasks.md`. Playground checks and maintainer approval are UI verification; browser suites and formal acceptance/study gates are excluded by the approved feature-scoped exception.

---

## Implementation Evidence (2026-11-24)

**Current status**: All 24 retained tasks are complete, including T030 and T040.
T031-T033 are complete under the approved playground scope, using the recorded
behavior checks below, not a newly executed browser suite. The maintainer approved
the current interface as usable and removed all required browser, formal acceptance,
and participant-study tasks. IDs are not renumbered.

**Retired IDs**: T002, T007, T011, T012, T017, T018, T024, T025, T028, T029, T034,
T035, T036, T037, T038, T039, T041, T042, T043. Existing browser/E2E code remains
optional. Historical evidence below is preserved, but its old browser/study gates
are superseded; no unexecuted test is reported as passing.

- T001/T003/T006: upstream Bootstrap integrity verified before trailer removal;
  shipped SHA-256 and provenance recorded in [README](../../README.md). The new asset
  assertion failed before stylesheet loading was implemented; all 3 app tests then passed.
- T007/T012/T018: focused browser tests authored, including selected navigation,
  stable announcements, applied/draft filters, detail retry/focus, and deferred responses
  superseded by close/page/filter/navigation. Their required executable before/after
  evidence was unavailable. These tasks are now retired, not treated as passing tests.
- T011/T017/T024/T025/T030: bundled Chromium lacks `libnspr4.so`.
  The maintainer declined browser/system dependency installation.
  Earlier collection of all 45 browser/E2E cases succeeded; collection is
  not execution. The E2E extension now includes 51 synthetic occurrences across
  pages, complete cross-tab request capture, external blocking, resource/header
  checks, keyboard selection/focus, and responsive layouts, but has not run.
- Supplementary VS Code integrated-browser smoke checks used locally served assets
  and controlled synthetic API responses, not execution of the required pytest suites.
  At 320/768/1440 CSS pixels, measured document widths were 305/753/1425: no
  horizontal overflow. Exact signed 64-bit boundary amounts and HTML-like source
  text remained literal. Applied summaries survived draft edits and paging;
  invalid amount ranges associated feedback with fields; retry requested the same
  occurrence ID twice; close returned focus; a late response after close was ignored.
  Import no-files state rendered all eight counts; unchanged polling produced zero
  status-text mutations; enabled navigation retained focus during forced same-view
  running polls. Normal and invalid selects computed `background-image: none`.
  These checks do not constitute a complete recovery matrix.
- T027: `uv build` succeeded. A task-owned clean virtual environment installed only
  the built wheel, reusing existing third-party dependencies without downloads.
  The imported application path was inside that environment, not the source checkout.
  ASGI serving returned root HTML and seven packaged HTML/CSS/JS/license assets
  with exact wheel bytes, no-store/CSP headers, expected shipped CSS hash, and MIT
  notice. Task-owned verification files/environment were removed afterwards.
- Available quality checks: full `uv run --locked ruff check .`,
  `uv run --locked ruff format --check .`, and strict Pyright passed.
  Targeted UI/transaction unit and real-PostgreSQL import/query tests: 104 passed.
  The first full non-browser run had 233 passes and one PostgreSQL connection-refused
  migration-setup error. That test passed in isolation; the complete rerun passed
  **234 tests** using `uv run --locked pytest --ignore=tests/browser
  --ignore=tests/integration/test_ui_browser_e2e.py -q`. No database fixture change
  or exception suppression was introduced. These non-browser results are engineering
  evidence under the scoped exception, not a newly executed full configured suite.
- Retired T029: no participant study was conducted or claimed. The maintainer's
  approval replaces the former study obligation.
- No backend/schema/provider/dependency changes. Financial amount parsing, import
  recovery/correlation algorithms, local-only CSP, and advisory limitations remain
  unchanged. Post-implementation extension configuration contains `hooks: {}`.

## Dependencies & Execution Order

### Phase Dependencies

Setup precedes foundation; T006 is the shared readiness checkpoint. Stories have
no new domain dependency on one another. Their HTML and CSS edits are deliberately
serialized to avoid conflicting work in the same files. Other story work can overlap.
Cross-cutting work starts after all three story checkpoints.

### Task Prerequisites

This table is authoritative; list order alone is not a dependency.

| Task | Required completed tasks |
|------|--------------------------|
| T001 | None |
| T003, T004 | T001 (setup checkpoint) |
| T005 | T003, T004 |
| T006 | T005 |
| T008 | T006 |
| T009, T010 | T008 |
| T013 | T008 (shared HTML ordering) |
| T014 | T013 |
| T015 | T013, T010 (shared CSS ordering) |
| T016 | T014 |
| T019 | T013 (shared HTML ordering) |
| T020 | T019 |
| T021 | T019, T015 (shared CSS ordering) |
| T022 | T020 |
| T023 | T022 |
| T026 | T009, T010, T015, T016, T021, T023 |
| T027 | T026 |
| T031 | T014, T016 |
| T032, T033 | T020, T023 |
| T040 | T016, T031 |
| T030 | T027, T032, T033, T040 |

### User Story Completion Graph

```text
T001 -> T003 + T004 -> T005 -> T006
                                      |
                +---------------------+---------------------+
                |                     |                     |
             US1 edits             US2 edits             US3 edits
                |                     |                     |
          playground              playground              playground
                +---------------------+---------------------+
                                      |
                                    T026
                                      |
                              T027 + T040
                                      |
                                    T030
```

Shared-file ordering additionally requires `T008 -> T013 -> T019` for HTML and
`T010 -> T015 -> T021` for CSS. This is integration ordering, not a need for new
US2/US3 domain functionality to complete US1.

### Within Each User Story

Check UI behavior in the playground and retain optional browser regressions where
useful. Required non-browser tests remain deterministic. Do not alter request
algorithms merely to make presentation checks pass.

### Parallel Opportunities

- Setup: T001.
- Foundation: T003 with T004 after setup.
- US1: T009 with T010 after T008.
- US2: T014 with T015 after T013 and T010.
- US3: T020 with T021 after T019 and T015.
- Cross-cutting: documentation and package checks after the relevant UI changes.
- Never run separate writers against shared `index.html`, `styles.css`,
  `transactions.js`, or evidence notes at the same time.

## Parallel Example: User Story 1

After T008 is complete:

```text
T009: Update selected navigation and focus in static/app.js.
T010: Finish shell and placeholder styles in static/styles.css.
```

## Parallel Example: User Story 2

After T013 and T010 are complete:

```text
T014: Render structured import status and outcomes in static/import.js.
T015: Finish import/count/recovery styling in static/styles.css.
```

## Parallel Example: User Story 3

After T019 and T015 are complete:

```text
T020: Implement applied-query and validation presentation in static/transactions.js.
T021: Finish filter/row/detail styles in static/styles.css.
```

## Implementation Strategy

### MVP First (User Story 1 Only)

Complete setup/foundation and T008-T010. Demonstrate the cohesive shell, unavailable
Chat, working existing task routes, selected navigation, and keyboard orientation.
Use playground checks and maintainer approval, not a formal acceptance study.

### Incremental Delivery

Add US2 and verify imports independently, then add US3 and verify browsing independently.
Complete the retained import-focus correction, package checks, and non-browser gates
before declaring the full feature complete.

### Parallel Team Strategy

Serialize shared HTML/CSS changes according to the prerequisite table; parallelize
only the different-file pairs explicitly identified above. Browser test authoring
is optional rather than a required work stream.

## Notes

- Every constrained presentation field is cited in its implementing task; no new
  persistence model or duplicate financial calculation is introduced.
- Existing service contracts, source text safety, BigInt/string exact amounts,
  opaque occurrence identity, recovery storage, deadlines, and generation guards
  remain regression requirements.
- Missing required Docker/non-browser checks are incomplete. Browser libraries,
  browser/E2E execution, participant availability, and formal acceptance matrices
  are not blockers under the approved scope.
- Mark tasks complete only after their described outcome is verified. Record
  implementation-phase evidence below without secrets or personal/financial data.

## Phase 7: Convergence

**Current scope**: The implementation corrections below have been checked in the
playground and satisfy the approved UI verification scope. Browser/study follow-ups
from this phase are retired; their test code remains optional. No browser/system
installation is required or authorized.

- [X] T031 HIGH: Keep rejected folder submissions classified as invalid input even when a prior run succeeded in `src/personal_financial_assistant/ui/static/import.js`. Preserve earlier-outcome wording, counts, field association, notices, and locking/correlation algorithms. Verify retained values and truthful status through polling in the playground; existing browser regression code is optional. Per FR-002, FR-008, US2/AC2, US2/AC5, T014, and T016. Recorded playground checks verified this correction.

- [X] T032 HIGH: Preserve visible focus through Next/Previous and list/category retries in `src/personal_financial_assistant/ui/static/transactions.js`, without focus theft after user movement or stale responses. Verify paging boundaries, failed/successful retries, and held responses in the playground. Per FR-005, FR-006, US1/AC4, and T023. Recorded playground checks verified this correction; browser tests remain optional.

- [X] T033 HIGH: Validate both date fields against the canonical four-digit ISO-date contract before search in `src/personal_financial_assistant/ui/static/transactions.js`. Preserve rejected values, associate field feedback, clear misleading results, and issue no unsupported-year search without changing backend rules. Verify rejected `10000-01-01` and valid inclusive bounds in the playground. Per FR-008, FR-009, US3/AC3, and T020. Recorded playground checks verified this correction.

### Convergence Implementation Evidence (2026-11-24)

**Status under the approved scope**: T031-T033 are complete from the recorded
playground checks. Former T034/T039 test changes remain optional regression code.
The evidence below is not a newly executed browser suite.

- T031: rejection presentation now takes precedence over an earlier successful
  import. Earlier outcomes are explicitly labeled, and rejection wording is not
  duplicated. Counts, field associations, recovery, and correlation are preserved.
- T032: keyboard paging and list/category retry move focus to a stable loading
  target before hiding the initiating button. Current-response completion restores
  an available button or the appropriate result/category target, but does not
  steal focus after the user moves elsewhere or the view becomes hidden.
- T033: both date fields reject unsupported non-four-digit years before search,
  preserving draft values and associating correction feedback with the fields.
  Backend date rules and exact monetary parsing are unchanged.
- T034: [transaction regressions](../../tests/browser/test_transactions.py) now
  cover category failure/retry, competing identical-looking occurrences with
  reversed detail replies, mismatched detail IDs, and recovery. The new
  [import regression](../../tests/browser/test_import.py) retains a previous
  successful outcome through a rejected submission and subsequent polling.
- T039: [real-server E2E monitoring](../../tests/integration/test_ui_browser_e2e.py)
  retains every static response, captures HTTP/request failures and all error
  console messages across both tabs, and preserves external-request blocking and
  CSP/no-store assertions. Exceptions are limited to the exact local favicon 404
  and `net::ERR_ABORTED` for specific import-poll requests already in flight on
  the deliberately reloaded page; unrelated failures remain fatal.
- New regressions were authored before the presentation corrections. The attempted
  focused import/date/paging pytest command failed during browser fixture setup:
  bundled Chromium could not load `libnspr4.so`. No behavior assertion executed,
  so no before-fix failure or pytest browser pass is claimed. The maintainer
  explicitly retained the installation restriction and authorized supplementary
  checks; no browser/system packages were installed.
- Available checks passed: `uv run --locked ruff check .`,
  `uv run --locked ruff format --check .`, and `uv run --locked pyright`.
  `uv run --locked pytest tests/unit/ui -q` passed **51 tests**.
  Browser/E2E collection succeeded with **56 cases**; collection is not execution.
- `uv build` produced the updated wheel and source distribution. A temporary
  extracted-wheel layout imported the application from that layout, not the
  source checkout. ASGI serving verified root HTML and seven static assets,
  exact current asset bytes, and unchanged CSP/no-store headers. This is an
  updated package-layout check, not a newly installed-environment claim.

Supplementary integrated-browser checks used freshly served local assets and
controlled synthetic responses, with no database or financial data:

| Scenario | Observed result |
|----------|-----------------|
| Prior success, rejected folder, subsequent polls | `invalid-input`, retained whitespace and eight counts, field invalid association, explicit earlier-outcome wording |
| From and To `10000-01-01` | Values retained, `aria-invalid` and `filter-error` association, zero additional searches, old rows cleared |
| Inclusive date bounds | `0001-01-01` and `9999-12-31` sent unchanged; exact signed 64-bit boundary amount remained readable |
| Category failure | Category selector and description filtering remained usable |
| Keyboard first/last paging boundaries | Focus remained on transaction status, not BODY |
| Failed/successful list retry | Focus returned to Retry on failure and transaction status on success |
| Failed/successful category retry | Focus returned to Retry on failure and the populated category selector on success |
| User moved focus during held paging response | Description retained focus after completion |
| Two identical-looking occurrences, reversed replies | Latest selected ID and evidence remained; HTML-like observation text created no image element |
| Mismatched detail ID, then retry | Selected context retained, wrong evidence absent, Retry exposed, correct evidence recovered |

Browser and participant-study checkpoints are now retired, not blockers. Required
non-browser checks remain in T030. No full configured pytest run is claimed.
Post-implementation hooks were checked:
`.specify/extensions.yml` still contains `hooks: {}`. Task-scoped browser mocks,
server, build outputs, and extracted-wheel temporary files are cleaned up.

## Phase 8: Convergence

**Retained correction**: The import-action focus gap is corrected and verified below. Former browser,
acceptance-matrix, participant-study, and full-browser release follow-ups from this
phase are retired under the approved exception. Non-browser quality work is
consolidated in T030.

**Original convergence evidence limits**: F1 was established by source inspection: `lock()` disables Start
and the folder field, successful status recovery hides Retry, resolution disables
its own control, and dismissal can hide Dismiss after refresh. None of these paths
handed off focus; only native folder-invalid handling explicitly focused the field.
The supplementary integrated-browser mock probe timed out before application
loading and provides no runtime confirmation. Its routes were removed and the page
returned to blank. Completed playground verification is recorded below.

**Ordering**: T040 follows T016/T031; T030 follows T040 and the package prerequisite
T027. No browser installation or formal acceptance/study gate is restored.

- [X] T040 HIGH: Preserve visible focus when import submission/recovery disables or hides the focused control in `src/personal_financial_assistant/ui/static/import.js`. Cover Start import, Retry status, Resolve unrecorded import, and Dismiss recovered outcomes; use a stable visible target and avoid focus theft after user movement. Preserve native invalid-folder focus, same-view poll stability, entered values, locks, correlation, and recovery algorithms. Update HTML and directly related documentation only as needed, and verify changed behavior in the integrated-browser playground. Browser regressions may be retained or extended optionally; no browser installation or formal acceptance matrix is required. Per FR-005, FR-007, FR-008, SC-005, US1/AC4, US2/AC2, US2/AC6, and T016 (partial).

### Final Implementation Evidence (2026-11-24)

- T040: the visible import-status region is programmatically focusable. A shared
  helper hands off focus immediately before the active import control is hidden or
  disabled, only while the status view is visible. Unaffected controls retain
  focus. Request, polling, locking conditions, correlation, and recovery algorithms
  are unchanged. The presentation contract and README document this behavior.
- The controlled Retry playground probe reproduced BODY focus before the fix and
  `import-status` focus after the fix, with a visible 3px outline. Freshly served
  local assets and synthetic responses also verified:

  | Scenario | Observed result |
  |----------|-----------------|
  | Start import, then failed run | Status retained focus; Start locked while running and unlocked after failure |
  | Empty folder validation | Folder field received focus |
  | Whitespace submission rejected with HTTP 422 | Status retained focus; whitespace and field-invalid feedback remained |
  | Resolve failure, then successful resolution | Status retained focus in both cases; recovery remained available after failure and hid after success |
  | Dismiss two recovered outcomes | Status retained focus; both synthetic pending IDs were removed |
  | Move focus to Import navigation during held Retry response | Navigation retained focus after Retry hid |
  | Focused folder disabled by a newly observed running import | Status received focus with a 3px outline; entered folder value remained |

- Five focused browser regression cases were authored before the correction and
  passed lint/type checks, but were not executed in pytest. Browser/E2E execution,
  formal acceptance matrices, and participant studies remain optional or retired
  under the approved exception; no browser/system packages were installed.
- T030: `uv run --locked ruff check .` passed;
  `uv run --locked ruff format --check .` reported **126 files already formatted**;
  `uv run --locked pyright` reported **0 errors and 0 warnings**.
  `uv run --locked pytest tests/unit/ui -q` passed **51 tests**.
  The complete retained suite,
  `uv run --locked pytest --ignore=tests/browser
  --ignore=tests/integration/test_ui_browser_e2e.py -q`, passed
  **234 tests in 111 seconds**, including real-PostgreSQL integration tests.
- `uv build` rebuilt the wheel and source distribution. The wheel was installed
  with `uv pip install --no-deps --no-index --target` into a fresh temporary
  target, reusing existing locked dependencies without downloads. Source-checkout
  import paths were excluded; every loaded application module came from that
  target. All eight packaged assets matched the current source in both installed
  wheel and source distribution. ASGI root HTML and seven static responses matched
  current content, including token substitution and unchanged CSP/no-store headers.
  The shipped Bootstrap SHA-256 matched the recorded provenance.
- No backend, schema, provider, dependency, financial, or security contract changed.
  Task-owned browser routes, synthetic pending IDs, playground server, installed
  target, and build outputs were cleaned up. Post-implementation extension
  configuration was checked and contains `hooks: {}`.

