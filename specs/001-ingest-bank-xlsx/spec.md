# Feature Specification: On-Demand Bank XLSX Ingestion

**Feature Branch**: `main` (unchanged; no branch-creation hook registered)

**Created**: 2026-11-22

**Status**: Ready for planning

**Input**: User description: "what we described in decision.md. Ingestion should be invoked on-demand, for now in a cli, and just reads all available xlsx and updates the current situation with what's inside them. The only thing to decide is what to use as key to make a transaction unique"

**Assessment**: [Approved manual-ingestion handoff](../../.specify/assessments/ingestion-mode/decision.md).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Import the available bank exports (Priority: P1)

The user downloads exports for their selected Intesa Sanpaolo account into an input folder and invokes ingestion from the command line. All eligible files are read, and transactions become persistent local records for subsequent financial analysis.

**Why this priority**: This supplies transaction information the assistant currently lacks, without a provider or background service.

**Independent Test**: Import synthetic bank-format workbooks into an empty transaction store and compare retained records with the expected transaction rows.

**Acceptance Scenarios**:

1. **Given** two valid exports for the selected account, **When** ingestion runs, **Then** both files are read and all eligible distinct transactions are retained with exact signed amounts, currencies, and dates.
2. **Given** a supported export with a preamble, the eight documented headings, and explanatory/blank footer rows, **When** ingestion runs, **Then** only transaction rows are imported, irrespective of the table header's row number.
3. **Given** booked and pending rows, **When** they are imported, **Then** source booking status is preserved and pending expenses are identified as ongoing rather than completed.
4. **Given** exports for different periods, **When** ingestion runs, **Then** all eligible history is imported without an artificial recent-month cutoff.

---

### User Story 2 - Repeat imports and refresh booking state (Priority: P1)

The user keeps older exports and adds overlapping ones. Repeated ingestion must not multiply previously imported transactions, erase older history, or revert booked transactions to pending.

**Why this priority**: Reading every file on each invocation is useful only if repeat imports preserve an accurate current situation.

**Independent Test**: Import overlapping synthetic exports repeatedly and in different file and row orders; compare counts, exact amounts, status, and reported uncertainties.

**Acceptance Scenarios**:

1. **Given** an already imported set of exports, **When** the same files are ingested again, **Then** no transactions are added and financial values and booking states are unchanged.
2. **Given** pending and booked observations of a transaction matching under the agreed identity rule, **When** both exports are ingested, **Then** one transaction remains, booked, independent of file order.
3. **Given** an export containing two otherwise identical transaction occurrences, **When** it and a duplicate copy are ingested, **Then** two occurrences are retained, not one or four.
4. **Given** a newer file omits a retained transaction, **When** ingestion runs, **Then** that transaction is not deleted or marked cancelled solely because of its absence.
5. **Given** a pending transaction and a booked observation whose association is ambiguous, **When** ingestion runs, **Then** the original stays pending, the booked observation is retained without a confirmed link, and uncertainty is reported without claiming the observations are definitely the same or different transactions.
6. **Given** exactly one pending occurrence and one booked observation sharing account, date, signed amount, and currency with no competing occurrences, **When** ingestion runs, **Then** that occurrence becomes booked even if operation, details, or category changed.

---

### User Story 3 - Understand results and failures (Priority: P2)

After invocation, the user sees whether ingestion completed, what changed, and what requires attention. Failures must not leave partially updated financial records.

**Why this priority**: The invoking command is the requested notification channel for now; incomplete data must not appear to be a successful refresh.

**Independent Test**: Run with empty, missing, unreadable, malformed, and mixed valid/invalid inputs, and with unavailable storage.

**Acceptance Scenarios**:

1. **Given** an empty input folder, **When** ingestion runs, **Then** it explicitly reports no eligible files and leaves records unchanged.
2. **Given** a valid and a malformed file, **When** ingestion runs, **Then** the invocation fails, identifies the offending file and structural problem without printing financial values, and persists no batch changes.
3. **Given** unavailable storage or interruption before completion, **When** ingestion cannot complete, **Then** failure is explicit and no partial batch changes persist.
4. **Given** a successful batch, **When** the command finishes, **Then** it reports files processed, rows read, transactions added/updated, observations unchanged, and unresolved observations.

### Edge Cases

- Repeated files, renamed copies, overlapping exports, and different file/row ordering.
- Two legitimate same-day purchases with identical visible fields.
- Pending transactions whose date, operation, details, or amount changes before booking.
- Older pending and newer booked observations; booked status must not regress.
- Transactions absent from later filtered exports; absence does not prove cancellation.
- Surrounding whitespace in headings or values, including `Categoria `.
- Missing headings, unknown booking states, invalid dates, missing currency, or invalid monetary values.
- Nonzero sub-cent EUR amounts; no silent rounding.
- Exports for another account, multiple accounts, or an unsupported layout.
- Corrupt, password-protected, unreadable, or changing files; temporary spreadsheet lock files.
- Valid empty tables, empty/nonexistent folders, unavailable storage, and concurrent invocations.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Ingestion MUST run only on demand from the CLI, accepting one local input folder and one selected account. Scheduled/background ingestion is excluded.
- **FR-002**: Each invocation MUST enumerate all regular XLSX files directly in that folder at its start, excluding temporary files beginning with `~$`. It MUST NOT search subfolders or follow file symlinks.
- **FR-003**: Ingestion MUST locate the supported Intesa table by headings, not a fixed row number, recognizing `Data`, `Operazione`, `Dettagli`, `Conto o carta`, `Contabilizzazione`, `Categoria`, `Valuta`, and `Importo`, with surrounding whitespace allowed.
- **FR-004**: The preamble and clearly non-transaction footer/blank rows MUST be distinguished from transaction rows. Malformed transaction rows MUST fail validation, not be silently skipped.
- **FR-005**: Each observation MUST retain its date, operation, details, account/card reference, booking status, source category, currency, and signed amount. Bank categories MUST remain suggestions, not authoritative or model-generated classifications.
- **FR-006**: Monetary values MUST be exact, with explicit currency and sign. Initial scope is EUR with cent precision: unsupported currency or nonzero sub-cent amounts MUST fail explicitly instead of being silently rounded or converted.
- **FR-007**: Only the selected account MUST be accepted. An export containing another account or multiple accounts MUST fail validation rather than silently mix accounts.
- **FR-008**: Transactions MUST be retained persistently within the local system and indefinitely. Later imports MUST NOT delete historical records merely because they are absent from an export.
- **FR-009**: Pending (`NON CONTABILIZZATO`) and booked (`CONTABILIZZATO`) states MUST remain distinguishable. Pending debits MUST be marked as ongoing expenses; pending credits MUST NOT be labelled expenses.
- **FR-010**: Matching MUST use selected account, transaction date, exact signed amount, and currency. These four fields define a candidate group, not a guarantee of one unique real-world transaction. Operation, details, booking status, and category MUST NOT be part of this matching key.
- **FR-011**: For a confirmed matching transaction, booked status MUST take precedence over pending regardless of file order; booked status MUST NOT regress.
- **FR-012**: Booking status and category MUST NOT create a new identity by themselves. Conflicting category suggestions MUST remain traceable to their observations rather than being silently overwritten.
- **FR-013**: Distinct occurrences within an export MUST be preserved, including identical-looking rows. Overlapping files and repeated/renamed copies MUST NOT multiply the same occurrences.
- **FR-014**: If exactly one pending occurrence and one booked observation share the matching key and no competing occurrence exists in the candidate group, ingestion MUST reconcile them as one booked transaction under the user's selected matching assumption. If association is ambiguous, existing pending records MUST stay pending; new booked observations MUST be retained without inventing a link or asserting they are definitely separate transactions. Uncertainty MUST be reported, not silently resolved. No interactive reconciliation workflow is required.
- **FR-015**: Validation and persistence failures MUST leave the batch unapplied: any invalid eligible file or processing failure means no transaction changes from that invocation persist. Source files MUST remain untouched.
- **FR-016**: The CLI MUST report success, explicit no-input completion, or failure. Validation/operational failures MUST have a non-success exit result. The summary MUST distinguish files processed, rows read, transactions added/updated, observations unchanged, and unresolved observations.
- **FR-017**: Error output MUST identify structural issues and file/row locations as needed without exposing account information, transaction details, monetary values, credentials, or raw financial payloads. No financial data may be sent to external services.
- **FR-018**: Changing or unreadable input files MUST cause explicit failure without partial updates. Concurrent invocations MUST not create duplicates or lost updates; an invocation unable to proceed safely MUST fail explicitly.
- **FR-019**: All eligible dates in supplied exports MUST be imported without a fixed lookback cutoff. Updated state reflects the provided observations, not a claim of live bank synchronization.
- **FR-020**: Unsupported layouts and transaction rows missing date, account, amount, currency, or booking state MUST fail validation. Empty optional description/category fields MUST be preserved as absent, not replaced with invented facts.
- **FR-021**: The four-field matching key MUST NOT enforce one record per candidate group. Ingestion MUST preserve evidence of multiple occurrences and only deduplicate observations whose equivalence is established by repeated input or matching occurrence evidence. Row/file ordering MUST NOT assign different identities to unchanged observations; competing candidates MUST remain unresolved rather than being merged solely because their keys match.
- **FR-022**: Changes to date, signed amount, account, or currency MUST NOT automatically link a new observation to an older pending transaction. The older transaction MUST remain pending; absence from later exports MUST NOT cancel it.
- **FR-023**: Connection settings MUST be loaded from a local `.env` file, with process environment variables taking precedence. Missing or invalid required settings MUST cause an explicit, sanitized configuration error rather than an implicit connection fallback.

### Key Entities *(include if feature involves data)*

- **Selected account**: The one account whose exports are accepted.
- **Bank export**: A workbook containing account/filter information and transaction observations; absence of a transaction is not proof of cancellation.
- **Transaction observation**: What one export reports about an occurrence, including its monetary amount, currency, descriptive fields, category, and booking state.
- **Transaction**: A retained occurrence, distinct from the four-field candidate group; multiple occurrences may have the same matching key.
- **Candidate group**: Observations sharing account, date, signed amount, and currency, within which occurrence matching may be unambiguous or unresolved.
- **Ingestion result**: Completion state, counts, and non-sensitive validation or reconciliation findings.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: One invocation processes every eligible file and retains 100% of eligible transaction occurrences, with dates, signed amounts, currencies, and booking states matching the reference examples.
- **SC-002**: Five repeat imports, including renamed copies and different file/row orders, create zero additional transaction occurrences and cause zero status regressions.
- **SC-003**: Every unambiguous pending-to-booked match results in one booked occurrence; every ambiguous match leaves the original pending record pending and reports uncertainty. Two purchases sharing the matching key remain two occurrences when their coexistence is evidenced by an export.
- **SC-004**: Every tested malformed-file, wrong-account, unavailable-storage, and interrupted-batch case preserves the prior transaction state and reports failure.
- **SC-005**: Every completed invocation reports its outcome and change counts; output exposes zero raw financial values or credentials.

## Assumptions

- One user operates locally. The provided Intesa XLSX is the supported layout; CSV, other banks, provider synchronization, scheduling, and a transaction-display interface are excluded.
- "All available XLSX" means files directly in a user-selected folder, not workbooks elsewhere on the machine.
- History is determined by the exports supplied; the user may start with a few months and add exports weekly/monthly. On-demand ingestion imposes neither a fixed frequency nor a history cutoff.
- "Updates the current situation" means adding observations and refreshing confirmed transaction state, not replacing all history or treating filtered exports as complete account snapshots.
- Identical visible fields do not prove real-world identity without bank IDs. The chosen rule must document its limitations and retain supporting observations.
- The user selected account + date + signed amount + currency matching and requested that unresolved records remain pending. A one-to-one candidate-group match is accepted as the same transaction even when descriptions change; this is an explicit heuristic, not bank-verified identity.
- If different same-key purchases never coexist in an export, the files may not distinguish them from repeated observations. The application cannot guarantee real-world uniqueness from this format. Indefinitely pending unresolved records are accepted for this version; no automatic cancellation or fuzzy matching across changed key fields is included.
- Failure notification is CLI output. Email, push notifications, automatic retry services, and notifications while the application is not running are excluded.
- Local storage is not implemented yet; planning must follow the existing constitution's storage, async execution, migrations, and verification constraints.
- Ordinary tests use synthetic workbooks representing the documented format; real bank exports and sensitive rows must not be committed or sent externally.
- The classifier itself is excluded; ingestion only retains categories as potential future suggestions.
- No elapsed-time, throughput, or workload-size benchmark is required. Workbook safety limits remain separate from performance goals.
