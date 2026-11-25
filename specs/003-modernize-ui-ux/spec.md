# Feature Specification: Modernize UI and UX

**Feature Branch**: `003-modernize-ui-ux`

**Created**: 2026-11-24

**Status**: Ready for planning

**Input**: User description: "improve and modernize ui and ux. Use some actual css library like bootstrap or tailwind, and if you need even a component library"

## Clarifications

### Session 2026-11-24

- Q: Which browsers must the redesigned interface support for this release? → Original answer (superseded below): Chrome only; current stable desktop Chrome is the required support and acceptance baseline.
- Updated scope: The maintainer removed required browser-runner, formal acceptance
  matrix, accessibility-review, and participant-study gates. Integrated-browser
  playground checks and the maintainer's usability approval are sufficient for UI
  validation. Existing keyboard, focus, labels, validation, and status behavior remains
  required; browser regression tests are optional.

### Scoped verification exception (approved 2026-11-24)

- **Approval and rationale**: The maintainer confirmed that the current interface is
  usable for their own use and approved playground validation instead of browser-suite
  execution, exhaustive acceptance matrices, or a five-person study.
- **Scope**: For `003-modernize-ui-ux` only, the Constitution IV and release-workflow
  requirements for browser-based verification are waived. Existing browser/E2E code
  remains optional coverage. Ruff, strict Pyright, non-browser unit and PostgreSQL
  integration tests, package checks, and financial/security constraints remain required.
- **Compatibility**: No application behavior, dependencies, global test configuration,
  or constitutional principles are changed. An excluded browser check is waived for
  this feature, not reported as a passing test.
- **Resolution condition**: Review this exception if the UI targets additional users
  or the maintainer reinstates browser-based release gates. Other features retain the
  ordinary constitutional quality gates.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Navigate a clear, consistent application (Priority: P1)

The local user opens a visually cohesive interface, understands which area is selected,
and can find the available import and transaction tasks without mistaking future chat
or reports for working features.

**Why this priority**: A clear application structure makes every existing task easier to
discover and gives the assistant a coherent identity without promising unavailable features.

**Independent Test**: Open the application at desktop and narrow viewport sizes, identify
the current area, and navigate between all available areas using pointer and keyboard.

**Acceptance Scenarios**:

1. **Given** no outstanding import requires attention, **When** the user opens the
   application, **Then** the initial Chat placeholder identifies chat and reports as
   unavailable and provides clearly labeled routes to Import and Transactions.
2. **Given** any selected area, **When** the user examines the interface, **Then** the
   current navigation item is identified visually and to assistive technology, and the
   page title, primary action, and supporting information have distinct visual hierarchy.
3. **Given** a narrow viewport, **When** the user navigates or operates a form, **Then**
   content reflows without overlapping controls or page-level horizontal scrolling,
   and all navigation and actions remain reachable.
4. **Given** keyboard-only navigation, **When** the user switches areas, **Then** focus
   remains visible, follows a logical order, and does not remain in hidden content.
5. **Given** an import may still be running, **When** the user tries to leave Import,
   **Then** the interface explains the navigation restriction without implying that
   another area opened; navigation becomes available when the existing rules permit it.

---

### User Story 2 - Import exports with understandable feedback (Priority: P1)

The user finds the local-folder input and import action, understands why an action is
unavailable, and can distinguish progress, completion, uncertainty, and failure from
the layout and explicit wording.

**Why this priority**: Imports change the retained financial history; improving their
presentation must increase clarity without weakening recovery or duplicate-start safeguards.

**Independent Test**: Exercise a successful import, repeated import, empty folder,
validation error, storage failure, and interrupted import using controlled outcomes.
Inspect the visible feedback and available recovery actions in each state.

**Acceptance Scenarios**:

1. **Given** the import screen is ready, **When** the user prepares an import, **Then**
   the labeled folder field, local-folder explanation, and primary Start import action
   are grouped together and are distinguishable from recovery actions.
2. **Given** invalid folder input, **When** the user submits it, **Then** an explanatory
   message is associated with the input and the entered value remains available to correct.
3. **Given** an import is running, **When** the user observes its progress, **Then**
   a textual running indicator is visible, duplicate submission is unavailable, and
   the interface does not invent a completion percentage or estimated finish time.
4. **Given** a successful or unchanged import, **When** results appear, **Then**
   all existing result counts are readable with their labels, and unresolved observations
   are explicitly distinguished from confirmed transaction changes.
5. **Given** no eligible files, a failure, or an unknown outcome, **When** the result is
   displayed, **Then** each state has distinct wording and appropriate existing next
   actions, without styling uncertainty or failure as success.
6. **Given** recovered import outcomes or an unrecorded request, **When** recovery is
   required, **Then** existing retry, resolution, and dismissal actions and their
   explanations remain accessible, including the warning to inspect transactions
   before retrying an unknown outcome.

---

### User Story 3 - Browse and filter readable transactions (Priority: P1)

The user scans recorded operations, dates, and amounts, applies understandable filters, and
inspects source evidence without losing track of the selected transaction or confusing
bank suggestions and uncertain information with confirmed facts.

**Why this priority**: Transaction browsing is the main working information view and
must remain readable as content and the number of filters grow.

**Independent Test**: Browse synthetic transaction pages with mixed statuses and long
source observations; combine filters, clear them, change pages, and inspect details
at desktop and narrow viewport sizes.

**Acceptance Scenarios**:

1. **Given** recorded transactions, **When** the list appears, **Then** recorded
   operations, dates, and exact signed amounts with currency are consistently
   aligned or grouped for comparison, with one chevron Details toggle. Positive
   amounts receive green card borders except in applied deposit-only results;
   EUR expenses of 99.95 or more receive red
   borders (signed amount <= -99.95 EUR); other negative and zero amounts remain neutral.
   Booking status and reconciliation state remain available in expanded details.
2. **Given** available filters, **When** the user narrows results, **Then** date,
   booking status, description, bank-suggested category, and absolute amount inputs
   have explicit labels; Apply and Clear actions are distinguishable; applied
   criteria remain visible while browsing results and pages. The filter form is in
   a keyboard-operable accordion, initially collapsed; toggling preserves drafts
   and applied criteria without issuing a search.
   Amount bounds start at zero, match either sign, and combine with an All /
   Withdrawals / Deposits selector. Withdrawals are negative, deposits positive,
   and zero belongs only to All. Recorded details appear as smaller single-line
   secondary text under operations, with an ellipsis on overflow and full text in
   expanded evidence. Missing and conflicting sources are identified explicitly.
3. **Given** an invalid date or amount range, **When** the user applies filters,
   **Then** an explanatory validation message identifies the relevant inputs,
   preserves their values, and does not present previous results as matches.
4. **Given** an occurrence is selected, **When** its details are displayed, **Then**
   the selected occurrence is identified by date, signed amount, and currency,
   source observations remain individually distinguishable, and long text is
   readable without obscuring navigation or actions.
5. **Given** pending credits, pending debits, unknown booking status, unresolved
   reconciliation, or conflicting categories, **When** transactions or details
   appear, **Then** existing financial meanings and uncertainty labels are preserved;
   color is never the only indication of a status.
6. **Given** empty history, no filter matches, loading, list failure, category failure,
   or detail failure, **When** that state occurs, **Then** the interface distinguishes
   it with explicit text and provides the applicable import, clear, or retry action;
   an unavailable category list does not prevent unrelated filters from being used.
7. **Given** more than one page, **When** the user uses Previous or Next,
   **Then** page controls are clearly located with the results and preserve the
   applied criteria; legitimate identical-looking occurrences remain separate.

### Edge Cases

- Long folder paths, descriptions, categories, and conflicting source observations
  must wrap or remain fully inspectable without displacing essential controls.
- At narrow widths, labels, status messages, details, and actions must remain
  readable and operable.
- An import-state check can delay initial navigation; its explanation must remain
  visible, and recovered imports take precedence over the usual Chat landing screen.
- Multiple recovered outcomes must remain distinguishable, and dismissal must not
  hide a still-running or unresolved request.
- Rapid filter, page, or detail changes must not display stale content as the current
  selection; loading feedback must describe the operation actually in progress.
- Zero, negative, and large signed amounts must retain exact values and currency;
  visual formatting must not change monetary calculations.
- Two distinct occurrences can have the same date, amount, and currency; inspection
  must still select the correct occurrence without merging their evidence.
- Financial records and errors must remain safe to display locally; no styling,
  fonts, icons, or other presentation resources may introduce external runtime requests.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The redesign MUST cover the application shell, Chat placeholder, Import,
  Transactions, source details, pagination, and their loading, validation, empty,
  unavailable, recovery, and failure states.
- **FR-002**: All covered areas MUST share consistent typography, spacing, surfaces,
  controls, and semantic status treatments. Each area MUST distinguish its heading,
  primary action, supporting text, and secondary or recovery actions.
- **FR-003**: Navigation MUST identify the selected area visually and accessibly.
  Chat MUST remain the initial unavailable placeholder unless existing import recovery
  requires Import; chat and reports MUST NOT appear operational.
- **FR-004**: All covered views MUST be operable at viewport widths from 320 to 1440
  CSS pixels, without clipped controls, overlapping content, or page-level horizontal
  scrolling. Long source information MUST remain fully inspectable.
- **FR-005**: All available tasks MUST be keyboard-operable with logical focus order,
  visible focus indicators, accessible control names, and focus outside hidden
  content. Any introduced dismissible overlay MUST support keyboard dismissal and
  return focus to its initiating control.
- **FR-006**: Covered views MUST retain explicit control labels, error identification,
  and textual status messages. Status meaning MUST NOT rely only on color, icons,
  or animation. Formal accessibility certification/review is not a release gate.
- **FR-007**: Import presentation MUST preserve local-folder submission, all result
  counts, duplicate-start prevention, navigation locks, unknown-outcome handling,
  and existing recovery controls. Running feedback MUST NOT invent unavailable
  progress measurements.
- **FR-008**: Input validation MUST preserve entered values, identify the relevant
  fields in explanatory messages, and make those messages available to assistive
  technology. Disabled or blocked actions MUST have a visible explanation when the
  reason is not evident from the current state.
- **FR-009**: Transaction filtering MUST retain existing inclusive date and exact
  nonnegative absolute EUR amount bounds, booking states, description matching, category matching,
  combined criteria, and clear-filter behavior. Applied criteria MUST remain visible
  during pagination and detail inspection.
  Direction MUST independently select all amounts, negative withdrawals, or positive
  deposits; zero is included only in All. Bounds MUST use exact cents and support
  the magnitude of the full signed-64-bit range without overflow.
  Pages default to 100 records. Centered First/Previous/Next controls MUST appear
  above and below results, remain visible with unavailable actions disabled, and
  leave the viewport position unchanged where page height allows when using visible
  top pagination. Bottom pagination MUST scroll smoothly to top pagination, using
  an instant jump instead when reduced motion is preferred.
  Focus MUST move to the corresponding top control without further scrolling.
  First MUST preserve applied filters.
- **FR-010**: Each displayed transaction MUST retain its exact signed amount,
  currency, date, and recorded operations in its primary row, with smaller, muted
  recorded details beneath operations and booking status
  and reconciliation state in details. A single labeled accordion toggle MUST
  expand/collapse details while retaining focus, without a separate Close button.
  Distinct occurrences MUST NOT be merged for visual simplicity.
- **FR-011**: Detail inspection MUST identify the selected occurrence and preserve
  separate source observations, missing values, conflicting evidence, bank-suggestion
  labels, and existing ongoing-expense distinctions without inventing certainty.
- **FR-012**: Loading, empty history, no matches, retrieval failure, category failure,
  and detail failure MUST have distinguishable messages and applicable next actions.
  Loading or stale content MUST NOT be presented as a completed current result.
- **FR-013**: The export-history limitation MUST remain readable in Transactions:
  records do not represent a live balance or guaranteed complete account history.
- **FR-014**: The redesigned interface MUST work without internet access once installed,
  with all presentation resources served locally. It MUST NOT introduce external
  runtime requests, telemetry, or disclosure of financial data, folder paths, filters,
  credentials, or raw sensitive error payloads.
- **FR-015**: The redesign MUST preserve the existing ingestion, persistence, security,
  and transaction-reading contracts. It MUST NOT introduce transaction editing,
  financial totals or analytics, new reports, working conversation, purchases,
  transfers, or credit commitments.
- **FR-016**: UI validation MUST use integrated-browser playground checks and
  maintainer usability approval. No browser installation, required browser-suite
  execution, exhaustive acceptance matrix, or participant study is required.
  Existing Playwright tests MAY be run as optional regression coverage.

### Key Entities *(include if feature involves data)*

- **Application area**: Chat placeholder, Import, or Transactions, with selection
  state and availability constrained by import status.
- **Import presentation**: Existing request state, labeled result counts, recovered
  outcomes, safe notices, and available recovery actions; no new import lifecycle.
- **Transaction browsing context**: Applied filters, current page, selected occurrence,
  and its source observations, together with loading, empty, validation, or error state;
  no new persistent financial entities.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The maintainer can find Import and Transactions and identify Chat and
  reports as unavailable; no timed navigation study is required.
- **SC-002**: Import results and unresolved-observation counts are understandable
  to the maintainer; no participant-count or timing threshold is required.
- **SC-003**: Filtering, detail inspection, paging, and clearing filters are usable
  by the maintainer; no minimum study dataset or formal task-completion study is required.
- **SC-004**: Playground inspection supports readable, operable layouts without
  clipped actions or page-level horizontal scrolling. An exhaustive three-width
  acceptance matrix is not required.
- **SC-005**: Existing keyboard controls retain visible, logical focus, including
  the pending import-action focus correction; no formal keyboard certification is required.
- **SC-006**: Playground checks show truthful import/filter/retrieval feedback and
  preserve exact transaction values and selected evidence. Existing browser regressions
  are optional, not mandatory acceptance checkpoints.
- **SC-007**: Presentation resources remain local and financial/security contracts
  remain unchanged, verified through applicable non-browser checks and playground
  inspection; no formal offline browser-session certification is required.
- **SC-008**: The maintainer approves the interface as clear and usable. This approval
  has been provided; no ratings survey or five-person study is required.

## Assumptions

- This is a presentation and interaction modernization of the existing local,
  single-user browser interface. The behavior baseline is
  [Financial Assistant Interface](../002-financial-assistant-ui/spec.md), including
  its import recovery and financial-evidence constraints.
- The user's explicit delivery constraint is adoption of an established CSS library,
  such as Bootstrap or Tailwind, rather than another entirely hand-written styling
  system. The concrete choice belongs in planning; an additional component library
  is optional and justified only by a current interaction need.
- Library adoption does not authorize a new application framework, remote runtime
  resources, or changes to the constitutional Python tooling and local-data rules.
  Any necessary asset preparation and library maintenance must be documented in
  the implementation plan and directly affected operational documentation.
- The existing English interface wording is retained and clarified as needed;
  translation, dark-mode selection, theme personalization, charts, new dashboards,
  and backend or schema redesign are outside this feature.
- The default visual theme is dark, with readable native controls and semantic
  status colors. No theme selector or persisted theme preference is introduced.
  A coherent default visual theme is sufficient. Cosmetic choices such as exact
  palette and whether desktop transactions use rows or cards are deferred to planning
  provided the readability, interaction, and responsive criteria are met.
- Existing ingestion and transaction services remain dependencies, not new feature
  scope. Evaluation uses synthetic financial information and controlled failures;
  presentation changes do not require live bank data or a model service.
- UI evidence consists of recorded playground checks and maintainer approval under
  the scoped exception above. Non-browser engineering checks still require actual
  passing results; waived browser tests must not be described as executed.
