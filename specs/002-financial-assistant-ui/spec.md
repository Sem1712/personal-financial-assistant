# Feature Specification: Financial Assistant Interface

**Feature Branch**: `main` (unchanged; no branch-creation hook registered)

**Created**: 2026-11-23

**Status**: Ready for planning

**Input**: A user interface to start import jobs and view and filter transactions, with chat as the eventual main part and reports available through chat or separately. Only import and transaction viewing are currently implementable.

## Clarifications

### Session 2026-11-23

- Q: What should the application show first while chat is not yet available? → A: Open the unavailable chat placeholder, with links to import and transactions.
- Q: Which additional transaction filters should the first version include beyond date, booking status, and description search? → A: Add bank category and signed amount range filters.
- Q: What should happen to an import if you leave its screen while it is running? → A: Keep the user on the import screen until it finishes.
- Q: How should you choose the exports to import in the first version? → A: Choose a local folder and import all eligible exports in it.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Start an import and understand its outcome (Priority: P1)

The user identifies a local folder containing their bank exports and starts an on-demand import. They see whether the import is running, completed, found no eligible files, or failed, and can understand what changed or needs attention.

**Why this priority**: Importing is the existing way to bring financial data into the application.

**Independent Test**: Start imports from folders with valid, empty, repeated, and invalid exports and compare the displayed outcomes with the retained transaction data.

**Acceptance Scenarios**:

1. **Given** a local folder containing supported exports, **When** the user starts an import, **Then** the interface indicates that the import is running and shows its outcome when finished.
2. **Given** an import completes successfully, **When** its result is shown, **Then** the user sees the counts of files seen, processed and unchanged; rows read; transactions added and updated; unchanged observations; and unresolved observations.
3. **Given** storage is available and a folder contains no eligible exports, **When** the user starts an import, **Then** the interface explicitly reports that no eligible files were found and does not present it as a data refresh.
4. **Given** an invalid export, inaccessible folder, unavailable storage, or competing import, **When** an import cannot proceed, **Then** the interface reports failure and a safe reason without claiming that the batch succeeded.
5. **Given** an import is already running, **When** the user attempts to start another from the interface, **Then** the second start is prevented and the ongoing state remains visible.
6. **Given** an import is running, **When** the user attempts to navigate to another area within the application, **Then** navigation is blocked until the import finishes and the interface explains why.
7. **Given** the interface is refreshed, closed, or disconnected during an import, **When** the user returns and its outcome cannot be established, **Then** the interface reports an unknown outcome rather than success or failure.
8. **Given** storage is unavailable and the selected folder is empty, **When** the user starts an import, **Then** the interface reports storage unavailability without claiming that the folder was checked or a run started.
9. **Given** workbook discovery, reading, or verification exceeds its time limit, **When** the import cannot complete, **Then** the interface reports a sanitized timeout failure if rollback is confirmed, or an unknown outcome if it cannot be confirmed.

---

### User Story 2 - Explore and filter recorded transactions (Priority: P1)

The user browses retained transaction occurrences, narrows the list to a useful subset, and inspects the recorded information without confusing uncertain matches or bank-suggested categories with confirmed facts.

**Why this priority**: Imported information is useful only when the user can find and understand it.

**Independent Test**: Populate the application with representative synthetic transactions, apply and clear filters, and compare the displayed occurrences and details with the retained records.

**Acceptance Scenarios**:

1. **Given** recorded transactions, **When** the user opens the transaction view, **Then** each occurrence is shown once with date, signed amount, currency, booking status or unknown status, and reconciliation state.
2. **Given** transactions across dates, booking states, descriptions, categories, and amounts, **When** the user combines filters, **Then** only occurrences matching all active criteria are shown; clearing filters restores the full list.
3. **Given** a transaction with source observations, **When** the user inspects it, **Then** available operation, details, and source category information are shown as reported by the bank, including conflicting values without inventing a definitive value.
4. **Given** an unresolved occurrence or a pending debit, **When** the transaction is displayed, **Then** uncertainty or ongoing-expense status is identified accurately; pending credits are not called expenses.
5. **Given** no recorded transactions or no matches for the active filters, **When** the user opens or filters the list, **Then** the interface distinguishes an empty history from an empty filtered result and offers an appropriate next action.
6. **Given** records cannot be retrieved, **When** the user opens or filters the list, **Then** the interface reports the failure rather than displaying an empty history.
7. **Given** an occurrence with differing source categories, **When** the user filters for any one of those categories, **Then** the occurrence is included and its source categories remain labeled as bank suggestions.

---

### User Story 3 - Navigate an interface prepared for future conversation (Priority: P2)

The user sees conversation as the prominent intended destination of the assistant while still being able to reach the working import and transaction views. The interface makes clear that conversation and reporting are not yet available.

**Why this priority**: The future assistant is the intended central experience, but working import and transaction tasks must not depend on unimplemented features.

**Independent Test**: Open the application without a conversational service and navigate to each available area.

**Acceptance Scenarios**:

1. **Given** the application is opened while chat is unavailable, **When** the initial screen appears, **Then** it shows the unavailable chat placeholder with links to import and transactions.
2. **Given** conversation or reports are not implemented, **When** the user encounters the future capability, **Then** the interface labels it as unavailable and does not accept a message or imply a report can be created or viewed.
3. **Given** conversation is unavailable, **When** the user navigates to import or transactions, **Then** those available tasks remain usable independently.

### Edge Cases

- An input folder is missing, unreadable, contains unsupported or malformed files, or contains no eligible exports.
- Storage is unavailable when an empty folder is selected; the UI reports storage unavailability rather than a no-files result.
- Workbook discovery, reading, or verification exceeds its time limit; cleanup and any uncertain commit outcome must be explicit.
- A repeated import changes nothing; unresolved observations must not be presented as confirmed transactions.
- An import fails or is interrupted; it must not appear successful or imply that partial batch changes were retained.
- The interface is refreshed, closed, or disconnected during an import; if its outcome cannot be established, the user must be told the outcome is unknown rather than being shown success or failure.
- A transaction has unknown booking status, conflicting source descriptions or categories, or an absent optional field.
- A date range is invalid; the user is told what to correct and no misleading result is shown.
- An amount range has invalid values or its minimum exceeds its maximum; the user is told what to correct and no misleading result is shown.
- Filters match no records, or retrieving records fails; these states must remain distinct.
- Two legitimate occurrences have identical visible attributes and must both remain visible.
- Transaction history may cover different export periods and is not a live bank balance.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: While chat is unavailable, the interface MUST open on its unavailable placeholder, with clearly accessible links to import and transactions and prominent navigation for the future conversation experience.
- **FR-002**: The interface MUST identify conversation and reports as unavailable; it MUST NOT offer working message submission, report generation, or report viewing in this release.
- **FR-003**: The user MUST be able to choose or enter a local input folder and explicitly start an on-demand import of all eligible exports directly in that folder. Selecting individual files is not supported.
- **FR-004**: The interface MUST communicate import progress as running and show one of success, no eligible files, failure, or unknown outcome when the operation completes. Storage must be available to start a UI import, even for an empty folder; otherwise the interface MUST report storage unavailability without claiming the folder was checked.
- **FR-005**: On successful import, the interface MUST show files seen, processed and unchanged; rows read; transactions added and updated; unchanged observations; and unresolved observations. It MUST identify unresolved observations as uncertain.
- **FR-006**: Import failures MUST show a safe, actionable reason when available, MUST NOT expose raw financial payloads or credentials in error messages, and MUST NOT be presented as successful or partially successful. Imports retain existing all-or-nothing batch behavior.
- **FR-007**: The interface MUST prevent a second import from being started through it while one is running; a conflict with another invocation MUST be reported as a failure.
- **FR-008**: The transaction view MUST list retained occurrences, not individual observations, with date, exact signed amount, currency, booking status including unknown, and reconciliation state. Distinct occurrences with identical displayed values MUST remain distinct.
- **FR-009**: The user MUST be able to filter by an inclusive date range, booking status (pending, booked, or unknown), case-insensitive text in source operation or details, bank-suggested category, inclusive absolute amount range in EUR, and All / Withdrawals / Deposits. Withdrawals are strictly negative and deposits strictly positive; zero belongs to All. Active filters MUST combine using all selected criteria; clearing them MUST restore all occurrences. Text and category filters each match an occurrence when any linked observation matches; the matching observations need not be the same.
- **FR-010**: The interface MUST reject an end date earlier than the start date with an explanatory validation message. Either date boundary MAY be omitted.
- **FR-011**: The user MUST be able to inspect available linked source operation, details, and categories for an occurrence. Conflicting source values MUST remain distinguishable; missing values MUST be identified as unavailable. Categories MUST be labeled as bank suggestions rather than authoritative classifications.
- **FR-012**: The interface MUST identify unresolved reconciliation and unknown booking status without inventing certainty. Only a pending debit that is not unresolved may be labeled an ongoing expense.
- **FR-013**: The transaction view MUST distinguish no recorded transactions, no filter matches, and retrieval failure, and provide a way to start an import, clear filters, or retry respectively.
- **FR-014**: After a successful import, the user MUST be able to view the updated transaction list without restarting the application.
- **FR-015**: The interface MUST indicate that records reflect supplied exports, not a live bank balance or a guarantee of complete account history.
- **FR-016**: Bank exports and displayed financial data MUST remain within the local system. The interface MUST NOT transmit them to external services or include them in logs.
- **FR-017**: The category filter MUST match the selected bank-suggested category against linked observations and MUST allow the user to find occurrences whose linked observations have no source category. An occurrence with conflicting categories matches each category reported for it.
- **FR-018**: Amount boundaries MUST accept exact nonnegative EUR values to cent precision, from zero through 2^63 cents, matching absolute amounts without losing stored signs. Either boundary MAY be omitted. Invalid values, negative values or a minimum greater than the maximum MUST produce an explanatory validation message. This supersedes the original signed-bound clarification.
- **FR-019**: While an import is running, the interface MUST keep the user on the import screen by blocking navigation to other application areas and explaining that the import must finish first. Once the operation finishes, navigation MUST be available again.
- **FR-020**: When the user returns after a refresh, closure, or disconnection during an import, if the interface cannot establish its outcome, it MUST identify the outcome as unknown rather than claim success or failure.

### Key Entities *(include if feature involves data)*

- **Import request**: A user-initiated operation for one local export folder.
- **Import result**: The operation's state, counts, and non-sensitive failure or reconciliation information.
- **Transaction occurrence**: A retained financial occurrence with a date, exact signed amount, currency, booking status, and reconciliation state.
- **Source observation**: An export's recorded description, suggested category, and status linked to an occurrence; multiple observations can disagree.
- **Transaction filters**: Optional date boundaries, booking status, description search, source category, absolute amount boundaries, and signed transaction direction applied to the displayed occurrences.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a usability test with at least five representative users and a prepared valid export folder, at least 4 of 5 users start an import and locate its outcome within two minutes without assistance.
- **SC-002**: For every tested successful, empty, empty with unavailable storage, repeated, invalid, timed-out, and conflicting import, the interface displays the correct outcome and all applicable result counts, with no failure presented as success.
- **SC-003**: For a reference set of at least 100 synthetic occurrences, every tested combination of date, status, text, category, absolute amount and direction filters returns exactly the expected occurrences, including distinct identical-looking occurrences and conflicting source categories.
- **SC-004**: For every tested unresolved occurrence, unknown status, pending debit, pending credit, and conflicting source category, the interface preserves the correct uncertainty and labeling.
- **SC-005**: In the same usability test, at least 4 of 5 users locate transaction filtering and correctly identify conversation and reports as unavailable without assistance.
- **SC-006**: In all tested empty-history, no-match, invalid-date, invalid-amount, and retrieval-failure cases, the interface displays the appropriate distinct state and next action.

## Assumptions

- The initial release is for one local user and the existing single-account, on-demand Intesa XLSX ingestion workflow. Selecting individual files, other banks, scheduled imports, transaction editing, analytics, purchase advice, conversation, and reports are out of scope.
- The user supplies a folder accessible to the application; existing ingestion rules determine eligible files, deduplication, account handling, atomicity, and source validation.
- The UI requires local storage before checking a folder so it can record the run; the existing command-line import continues to report an empty folder without requiring storage.
- The existing ingestion capability and local transaction storage are dependencies. A transaction-reading capability must be delivered as part of this feature; it is not assumed to exist already.
- Conversation is the prominent future destination and initial screen, but this release presents an explicitly unavailable placeholder rather than a simulated bot. Whether future reports belong within chat or a separate view is deferred to that future feature.
- Filtering and inspection operate on recorded occurrences and their linked observations. Source information is not a model-generated classification or a statement that all exports agree.
- The application displays sensitive transaction information only as needed for the local user's task; operational errors and logs remain sanitized.
