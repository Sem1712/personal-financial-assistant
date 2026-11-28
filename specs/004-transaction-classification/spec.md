# Feature Specification: Transaction Classification and Context

**Feature Branch**: `main` (unchanged; no branch-creation hook registered)

**Created**: 2026-11-28

**Status**: Ready for planning

**Input**: Extend existing transactions with independent transaction type, category, budget treatment, classification status, confidence and source, and optional user annotations and explanations, while preserving original imported data independently of enrichment.

## Clarifications

### Session 2026-11-28

- Q: How should users access and edit transaction classifications in this feature? → A: Add viewing to the existing interface, but defer user editing.
- Q: Where should classification information appear in the existing transaction interface? → A: Show classification and notes in transaction details only.
- Q: Which classifications should automatic updates be prevented from replacing? → A: Allow automatic replacement of any classification.
- Q: Should status, confidence and source be recorded separately for each classification dimension? → A: Record status, confidence and source separately for each dimension.
- Q: Whose explanations should this feature be able to retain? → A: Retain user and AI explanations only, with their sources identified.
- Q: How precise may classification confidence be? → A: Up to two decimal places; reject greater precision without rounding.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Record independent classifications (Priority: P1)

Application capabilities can associate financial meaning with an existing transaction without replacing the bank's original information. The user can view the recorded information in the existing transaction interface. Transaction type, category and budget treatment can describe different aspects of the same transaction.

**Why this priority**: Reliable classifications are the foundation for future financial analysis and guidance.

**Independent Test**: Record and retrieve several combinations of classifications on existing synthetic transactions, including partially classified transactions and transactions with identical imported values.

**Acceptance Scenarios**:

1. **Given** a transaction, **When** its type is recorded as expense, its category as groceries and its budget treatment as extraordinary, **Then** all three values are retained and can be retrieved together.
2. **Given** a classified transaction, **When** only its budget treatment changes, **Then** its type and category remain unchanged.
3. **Given** a transaction with no classification, **When** it is retrieved, **Then** each missing dimension is explicitly unclassified rather than inferred from the amount or bank category.
4. **Given** two separate transactions with identical visible imported values, **When** one is classified, **Then** the other remains unchanged.
5. **Given** a classified transaction, **When** the user opens its details in the existing transaction interface, **Then** its classification dimensions and their available metadata are visible without an editing control.

---

### User Story 2 - Understand and correct classification evidence (Priority: P1)

The user can understand whether each classification is provisional or confirmed, where it came from and how confident its origin was. Application capabilities can record a user correction without confusing a suggestion with a confirmed fact; editing in the interface is deferred.

**Why this priority**: Financial guidance must not present uncertain or automated interpretation as verified fact.

**Independent Test**: Record classifications from each supported source with different statuses and confidence values, retrieve them, and replace one with a user correction.

**Acceptance Scenarios**:

1. **Given** an AI-sourced provisional category with a stated confidence, **When** it is retrieved, **Then** the category, provisional status, AI source and confidence are distinguishable from the imported bank category.
2. **Given** a rule-sourced category and a user-sourced budget treatment, **When** the transaction is retrieved, **Then** the source and status for each dimension remain distinguishable.
3. **Given** a confirmed user classification, **When** an automated update supplies a valid replacement, **Then** the new value and its own status, source and confidence replace the previous classification for that dimension.
4. **Given** a classification with no confidence supplied, **When** it is retrieved, **Then** confidence is shown as unavailable rather than as an invented value.
5. **Given** an invalid classification value or confidence, **When** an update is submitted, **Then** it is rejected with a reason and the prior enrichment remains unchanged.
6. **Given** a confidence with more than two decimal places, **When** an update is submitted, **Then** it is rejected without rounding and the prior enrichment remains unchanged.
7. **Given** the outcome of an update cannot be established after a storage interruption, **When** the result is reported, **Then** it is identified as unknown, not as a confirmed failure or success, and the current state must be checked before retrying.

---

### User Story 3 - Retain context and original evidence (Priority: P2)

Application capabilities can record optional user annotations and user- or AI-provided explanations, and the user can view them alongside the bank's original observations, even after classification changes or later imports. Editing notes in the interface is deferred.

**Why this priority**: Personal context and unaltered source evidence make classifications understandable and auditable.

**Independent Test**: Add and change context on an imported transaction, reimport overlapping observations, and compare the retained enrichment and source data with their prior values.

**Acceptance Scenarios**:

1. **Given** a transaction with bank-suggested categories and other source observations, **When** an application capability records a user annotation and a user explanation, **Then** those notes are retained separately from the bank's data.
2. **Given** a classified and annotated transaction, **When** an overlapping export is imported or a pending occurrence becomes booked under existing matching rules, **Then** its enrichment remains attached to that occurrence and its source observations remain available.
3. **Given** observations with conflicting bank categories, **When** enrichment is recorded or changed, **Then** the conflicting bank categories remain independently available and are not represented as the chosen classification.
4. **Given** a transaction with optional notes, **When** an application capability clears one note, **Then** that note is absent and the other notes, classifications and imported data remain unchanged.
5. **Given** a transaction with a user explanation, **When** an AI explanation is recorded, **Then** both explanations remain available with their sources identified.

### Edge Cases

- Existing and newly imported transactions have no enrichment; missing data must not be mistaken for an expense, ordinary budget item, or confirmed classification.
- Any dimension may be absent while the others have values; sources, confidence and status must not leak between dimensions.
- Invalid type, budget treatment, status, source, empty category, or confidence outside the inclusive 0–100 percent range or with more than two decimal places must be rejected without rounding or a partial update.
- A value is cleared: its status becomes unclassified and its source and confidence are absent.
- Unknown or conflicting source observations, pending and unresolved transactions, and distinct same-looking occurrences retain existing identity and reconciliation semantics.
- A rejected update or a storage failure with confirmed rollback must be reported without claiming success or changing imported or previously saved data. An unknown commit outcome must be reported as unknown, without claiming rollback or success.
- An automatic update may replace a user-sourced or confirmed classification; the resulting value must carry the new classification's own metadata.
- Reimport and pending-to-booked reconciliation must not erase enrichment or modify previously retained source observations.
- AI and user explanations can coexist; a rule-sourced explanation is rejected without changing existing context.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST associate enrichment with each existing transaction occurrence independently of its imported observations, including occurrences that are pending or unresolved.
- **FR-002**: The system MUST support transaction types expense, income, transfer and refund, each independently selectable from category and budget treatment.
- **FR-003**: The system MUST support a category as nonempty text, including groceries, housing and transport, without limiting categories to those examples. A bank-provided category MUST remain source evidence, not automatically become the chosen category.
- **FR-004**: The system MUST support ordinary, extraordinary and excluded budget treatments independently of type and category. This feature records treatment; it does not calculate budgets.
- **FR-005**: Each dimension MUST support unclassified, provisional and confirmed statuses independently. A missing value MUST be unclassified; a populated value MUST be provisional or confirmed.
- **FR-006**: Each populated dimension MUST identify its source as AI, rule or user. A dimension MAY have a confidence expressed as a percentage from 0 to 100 inclusive with at most two decimal places; values with greater precision MUST be rejected without rounding. Missing confidence MUST remain explicitly unavailable. An unclassified dimension MUST have neither source nor confidence.
- **FR-007**: The system MUST accept and retain a dimension's value and associated status, source and optional confidence together, and MUST allow a user to correct or clear a dimension without changing unrelated dimensions.
- **FR-008**: A valid AI or rule update MAY replace any current classification, including a confirmed or user-sourced value. The resulting dimension MUST reflect the replacement's value, status, source and optional confidence rather than retaining the previous metadata.
- **FR-009**: The system MUST support an optional user annotation and separate optional user and AI explanations for each transaction, including adding, changing and clearing each independently without changing the others or the classification dimensions. Rule-sourced explanations MUST be rejected.
- **FR-010**: Retrieval MUST distinguish each enrichment value and its status, source and confidence from imported transaction facts and bank-suggested categories, including conflicting linked observations.
- **FR-011**: Imported observations and their existing transaction relationships MUST remain available and unchanged by enrichment operations. Existing amounts, currencies, dates, booking states and reconciliation behavior MUST NOT be changed by classification.
- **FR-012**: Existing transactions and new imports MUST remain available with all dimensions unclassified until explicitly enriched; ingestion MUST NOT infer enrichment from a source category or amount.
- **FR-013**: Repeated imports and confirmed pending-to-booked reconciliation under existing rules MUST preserve enrichment for the retained occurrence and preserve existing source observations. No enrichment may be transferred between distinct or ambiguously matched occurrences.
- **FR-014**: Invalid values, missing required classification metadata and storage failures MUST be reported explicitly. A rejected update or an update with confirmed rollback MUST leave the entire requested enrichment update and all source observations unchanged. When the commit outcome cannot be established, the system MUST report an unknown outcome rather than success or confirmed failure, and require the current state to be read before retrying.
- **FR-015**: Enrichment and financial source data MUST remain local; errors and logs MUST NOT expose raw financial payloads, user notes or credentials.
- **FR-016**: The existing transaction detail view MUST allow the user to view classification dimensions, their status, source and confidence, and any annotation and explanations alongside independently labeled bank observations. Each explanation MUST identify whether it came from the user or AI. Missing values MUST be identified as absent. Classification and notes MUST NOT be added to the transaction list, and the interface MUST NOT offer classification or note editing in this feature.

### Key Entities *(include if feature involves data)*

- **Transaction occurrence**: A retained financial occurrence with its established identity, financial facts, booking state and reconciliation state.
- **Source observation**: Imported evidence linked to an occurrence, including the bank's descriptions, category and booking status; multiple observations can disagree.
- **Classification dimension**: One of transaction type, category or budget treatment, with its own value, status, source and optional confidence.
- **Context**: An optional user annotation and optional user and AI explanations attached to an occurrence, separate from both source observations and classification dimensions.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a reference set of at least 100 synthetic transactions covering all types and budget treatments, every tested combination of independent dimensions and metadata is retrieved exactly as recorded.
- **SC-002**: In all tested existing, newly imported and partially enriched transactions, absent dimensions and confidence are identified as absent without invented values.
- **SC-003**: Across five repeated overlapping imports and a pending-to-booked reconciliation, 100% of previously recorded enrichment and original observations remain available and unchanged except for existing permitted booking-state updates.
- **SC-004**: Every tested invalid update reports the failure and leaves all previously recorded enrichment and imported observations unchanged; every tested valid automatic replacement shows the new value and its own metadata.
- **SC-005**: In a task exercise with at least five representative users, at least four correctly distinguish bank suggestions from classification, identify classification source and uncertainty, and describe the meaning of excluded budget treatment using the retrieved information.

## Assumptions

- The existing local, single-user transaction and ingestion workflows are prerequisites. This feature extends the information they can retain and retrieve; it does not change bank import formats, matching rules or transaction identity.
- The scope includes the classification and context model, its accessible read/update behavior, and read-only presentation in the existing transaction detail view. List presentation, editing in the interface, automatically generating classifications, defining a rule engine, analytics, budget calculations and purchase advice are separate work.
- Each occurrence has at most one current value per dimension. Status, source and confidence belong to the dimension, so different dimensions can have different origins or certainty. Historical classification revisions are not required.
- Automatic updates may replace any current classification without retaining its prior value; the current source and status identify the replacement rather than its predecessor.
- Unclassified means no value has been assigned; provisional means a value is awaiting confirmation; confirmed means a value has been accepted. Confirmation does not imply bank verification.
- Confidence is optional for every source and represents the origin's stated confidence, not a guarantee of correctness. No confidence threshold or automatic confirmation is assumed.
- An annotation is a user's personal note. An explanation is a reason or context supplied by the user or AI; each source can have one current explanation per transaction. These are optional free text; no automated explanation generation is required.
- Categories are descriptive labels rather than a fixed taxonomy. Category normalization, category hierarchy and category management are outside this scope.
- An excluded budget treatment is recorded as the user's intended treatment for future budget calculations; no budget calculation behavior is introduced here.
