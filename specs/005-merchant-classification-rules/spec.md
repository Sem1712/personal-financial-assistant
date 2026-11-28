# Feature Specification: Merchant Identification and Classification Rules

**Feature Branch**: `main` (unchanged; no branch-creation hook registered)

**Created**: 2026-11-28

**Status**: Ready for planning

**Input**: Normalize merchant descriptions, support aliases and matching patterns, merchant category defaults, user preferences and transaction overrides, with explicit precedence and protection for user-confirmed rules against AI-generated suggestions.

## Clarifications

### Session 2026-11-28

- Q: How should users create rules, set transaction overrides, and review AI suggestions? → A: Provide service-level capabilities only; defer all user-facing controls.
- Q: When an AI-generated rule conflicts with a confirmed rule for some transactions, where should the AI rule be blocked? → A: Block and report each conflicting application until approved; allow non-conflicting applications.
- Q: When should the system apply merchant and category rules to newly imported transactions? → A: Automatically evaluate newly imported transactions; reapply to existing transactions only on request.
- Q: What should happen if automatic rule evaluation fails during an import? → A: Keep successfully imported transactions, report failed evaluations, and allow explicit retry.
- Q: What kinds of merchant description patterns should rules support? → A: Exact aliases and literal contained-text patterns only.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Identify merchants consistently (Priority: P1)

An application capability records that several bank descriptions identify the same merchant, so future transactions can be understood consistently without changing the original bank information.

**Why this priority**: Reliable merchant identification is the foundation for reusable classification.

**Independent Test**: Create a merchant with an alias and a matching pattern, then identify synthetic transactions with different descriptions and inspect both the resolved merchant and original descriptions.

**Acceptance Scenarios**:

1. **Given** a merchant with aliases `Corner Shop` and `CORNER SHOP 123`, **When** transactions containing those descriptions are identified, **Then** both resolve to that merchant and their original descriptions remain unchanged.
2. **Given** an enabled merchant pattern for the literal text `Corner Shop`, **When** a normalized description contains that text, **Then** it matches the merchant unless another eligible merchant conflicts.
3. **Given** a description with no matching merchant, **When** identification is attempted, **Then** the transaction remains unidentified and the outcome says no match was found.
4. **Given** equally ranked matching rules identify different merchants, **When** identification is attempted, **Then** the conflict and candidates are reported and no merchant is chosen automatically.

---

### User Story 2 - Apply reusable category rules (Priority: P1)

Application capabilities record user-directed merchant defaults and classification preferences so recurring transactions receive useful categories, while an individual transaction can be assigned a different category.

**Why this priority**: Reusable rules reduce repeated work without preventing exceptions.

**Independent Test**: Apply a merchant default, a matching preference and a transaction-specific override to synthetic transactions, then inspect each result and its reason.

**Acceptance Scenarios**:

1. **Given** an identified merchant with an enabled default category and no higher-priority category rule, **When** classification is applied, **Then** the transaction receives the default category with rule provenance.
2. **Given** a matching user preference and a different merchant default, **When** classification is applied, **Then** the preference wins and the result identifies the winning rule.
3. **Given** a transaction-specific category override and matching reusable rules, **When** classification is applied, **Then** the override wins and remains unchanged.
4. **Given** equally ranked applicable rules with different categories, **When** classification is applied, **Then** the conflict and candidates are reported and the existing category is not replaced.
5. **Given** rules with no applicable category, **When** classification is applied, **Then** no category is invented and any existing category remains unchanged.

---

### User Story 3 - Maintain rules without losing confirmed decisions (Priority: P1)

Application capabilities can create, inspect and maintain merchant and classification rules, including recording explicit user decisions. AI suggestions remain distinguishable from user-confirmed decisions and cannot silently replace them.

**Why this priority**: Automation is useful only when user-confirmed decisions remain trustworthy.

**Independent Test**: Create, confirm, edit and disable rules through the supported interactions; submit conflicting AI changes and check both the reported outcome and persisted rules.

**Acceptance Scenarios**:

1. **Given** a user-confirmed rule, **When** an AI-generated suggestion attempts to change or disable it, **Then** the confirmed rule remains unchanged and the suggestion is reported for user review.
2. **Given** an AI-generated rule that conflicts with a user-confirmed rule on one transaction but not another, **When** both are evaluated, **Then** the conflicting application is blocked and reported for review while the non-conflicting application can proceed.
3. **Given** an AI-suggested rule, **When** the user explicitly confirms it, **Then** it becomes user-confirmed and receives the same protection as other confirmed rules.
4. **Given** an existing rule, **When** the user edits or disables it, **Then** the requested change is retained, reported and used in subsequent evaluations.
5. **Given** an invalid rule or a failed save with confirmed rollback, **When** the change is submitted, **Then** the reason is reported and previously saved rules and classifications remain unchanged.
6. **Given** an AI-generated proposal forwarded by a classification capability, **When** it conflicts with a confirmed rule, **Then** it remains identified as AI-generated and the confirmed rule receives the same protection.
7. **Given** a reviewed conflict, **When** another applicable rule, the transaction override or current category changes the reviewed result before approval, **Then** approval is rejected as stale and the user must review the updated result.

---

### User Story 4 - Explain and control reclassification (Priority: P2)

A user or classification capability can apply the current rules to selected existing transactions and understand the result, without unexpected changes to unrelated transactions.

**Why this priority**: Rules must remain useful for past transactions while preserving deliberate exceptions.

**Independent Test**: Change a rule, compare existing transaction classifications before and after explicit reapplication to a selected set, and inspect resolved and conflicting outcomes.

**Acceptance Scenarios**:

1. **Given** a rule is edited, **When** no reapplication has been requested, **Then** existing transaction categories remain unchanged.
2. **Given** selected transactions with and without overrides, **When** current rules are explicitly reapplied, **Then** only selected eligible transactions are updated and overrides remain unchanged.
3. **Given** a classification result, **When** its explanation is inspected, **Then** it distinguishes the matched merchant, the winning category rule or override, and any unresolved conflict from original bank evidence.
4. **Given** a selected transaction with an unresolved rule conflict, **When** rules are reapplied, **Then** its existing category remains unchanged and the conflict is reported alongside outcomes for the other selected transactions.
5. **Given** a newly imported transaction, **When** the import is processed, **Then** current merchant and category rules are evaluated for that transaction and the outcome is reported.
6. **Given** an import that successfully retains transactions, **When** rule evaluation fails for an occurrence, **Then** the imported data remains available, the failure is reported for that occurrence, and evaluation can be explicitly retried.

### Edge Cases

- Blank descriptions or patterns are rejected when creating matching rules; blank transaction descriptions yield no match rather than a guessed merchant.
- Normalization ignores case and surrounding or repeated whitespace only; it does not strip meaningful characters or alter stored source descriptions. Pattern matching uses literal text, not an interpreted expression.
- An exact alias takes precedence over a substring pattern; equally ranked matches to the same merchant are not a merchant conflict. Equally ranked matches to different merchants remain unresolved.
- A preference and merchant default may have the same category; precedence still identifies the winning rule. Equally ranked rules with the same category produce that category and identify all winning rules.
- Disabled rules do not participate. Disabling a merchant or rule does not erase historical source data, existing classifications or transaction overrides.
- An AI suggestion that would alter or disable a confirmed rule remains pending until explicitly approved. An AI rule that conflicts with a confirmed rule is blocked and reported only for each conflicting transaction, regardless of precedence; it remains usable elsewhere and visibly AI-originated.
- A classification capability forwarding or transforming an AI-generated suggestion does not make it a non-AI suggestion. If its generation origin cannot be established, the proposal is rejected with a reason.
- Rules of different kinds can have the same local identifier; conflicts, approvals and results must still identify the specific rule kind and rule.
- A user-confirmed rule can be changed or disabled by an explicit user action; confirmation is not inferred from an automated action.
- Transaction overrides are specific to a retained transaction occurrence, not to all occurrences with the same description; clearing one allows reusable rules to apply on a later evaluation.
- Reimport and pending-to-booked reconciliation follow existing occurrence identity rules. They must not move overrides between distinct or ambiguous occurrences.
- An overlapping import or pending-to-booked reconciliation of an existing occurrence is not a newly imported occurrence and does not automatically reclassify it.
- Failure to evaluate a rule does not undo a successful transaction import. An evaluation with an unknown outcome must be checked before retrying.
- If an operation's storage outcome is unknown, the system reports that uncertainty and requires current state to be checked before retrying; it does not assert success or rollback.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST retain a canonical merchant name and allow a user, agent or classification capability to create, inspect, edit and disable merchants, aliases and matching patterns.
- **FR-002**: The system MUST identify a merchant from transaction descriptions using enabled exact aliases and literal substring patterns after case-insensitive comparison and trimming and collapsing whitespace. It MUST preserve original imported descriptions and other source observations.
- **FR-003**: After applying the confirmed-rule safeguard in FR-011, exact alias matches MUST outrank substring pattern matches. If highest-ranked matches identify different merchants, the system MUST report the candidates and leave the merchant unresolved; it MUST NOT select one arbitrarily. No matching description MUST produce an explicit no-match outcome.
- **FR-004**: A merchant MUST support an optional default category. A user, agent or classification capability MUST be able to create, inspect, edit and disable that default.
- **FR-005**: The system MUST support reusable classification preferences that match either a specified merchant or a normalized description by exact text or literal substring, and assign a nonempty category. A user, agent or classification capability MUST be able to create, inspect, edit and disable preferences.
- **FR-006**: The system MUST support a user-set category override for an individual transaction occurrence, including inspecting, changing and clearing it independently of reusable rules and other occurrences.
- **FR-007**: On classification, category precedence MUST be transaction-specific override, then matching classification preference, then identified merchant's default. Within a preference, merchant-specific and exact-description matches MUST have equal priority above substring-description matches. Disabled or inapplicable rules MUST be excluded.
- **FR-008**: Within the same precedence and specificity level, user-confirmed rules MUST outrank unconfirmed rules. If the remaining highest-ranked rules have different categories, the system MUST report all candidates and leave the existing category unchanged. If their categories agree, the system MUST apply that category and identify all winning rules.
- **FR-009**: Merchant ambiguity MUST prevent applying a merchant-dependent preference or default; a description-based preference or transaction override MAY still apply according to category precedence. If no eligible category rule applies, the existing category MUST remain unchanged and the outcome MUST state that no rule applied.
- **FR-010**: Each rule and merchant matching entry MUST retain its generation origin, enabled state and whether a user has confirmed it. The system MUST distinguish AI-generated suggestions from user-confirmed decisions when rules are inspected and evaluated. An AI-generated proposal MUST retain its AI origin when forwarded or transformed by another capability; a proposal with unestablished origin MUST be rejected explicitly.
- **FR-011**: AI-generated changes MUST NOT modify, disable or delete a user-confirmed rule or matching entry, directly or by disabling its merchant, without explicit user approval; such changes remain pending for review. During evaluation, an AI-generated rule or matching entry that conflicts with a confirmed one MUST be blocked for that transaction and reported for review, regardless of precedence, unless the user has explicitly approved that application. The AI entry MAY remain active for non-conflicting transactions. A conflict exists when both entries apply to that transaction and specify different categories or merchants, respectively. The safeguard MUST also apply when a rule is confirmed after an AI entry was created. Confirmation and approval MUST be explicit user actions.
- **FR-012**: Users MUST be able to inspect pending suggestions and conflicts and explicitly approve or reject them through service-level capabilities. Approval MUST identify the affected confirmed decision and resulting change before it takes effect. If a change since review alters the affected decisions or reviewed result, approval MUST be rejected as stale and require a new review. Approval of an AI rule's conflicting application applies only to the identified transaction and confirmed decision; rejection MUST leave existing decisions unchanged. Conflicts and outcomes MUST distinguish rules of different kinds even when their identifiers match.
- **FR-013**: Rule creation, editing, confirmation, approval, rejection and disabling MUST report their outcome. Invalid input MUST be rejected with a reason without partial changes; storage failures MUST be reported without claiming success. When commit outcome is unknown, the system MUST report it as unknown and require the current state to be read before retrying.
- **FR-014**: The system MUST automatically evaluate current merchant and category rules for newly imported transaction occurrences and report the outcomes. A failed evaluation MUST NOT undo a successful import; the system MUST identify affected occurrences, report the failure and allow explicit retry. Rule changes, overlapping reimports and pending-to-booked reconciliation MUST NOT automatically reclassify already recorded occurrences. The user or an application capability MUST be able to explicitly apply current rules to selected existing transactions; only selected eligible occurrences may change and transaction-specific overrides MUST remain intact.
- **FR-015**: Each evaluation MUST report the identified merchant or no-match/conflict outcome, selected category or unchanged outcome, applicable winning rules or override, and any unresolved conflicts. A category applied from reusable rules MUST record rule source and an appropriate provisional or confirmed status without inventing confidence; an override MUST retain user source.
- **FR-016**: Classification and identification MUST NOT alter imported observations, amounts, currencies, transaction identity, booking or reconciliation behavior, or unrelated classification dimensions. Reimport and existing pending-to-booked reconciliation MUST preserve rules and overrides for retained occurrences and MUST NOT transfer overrides across ambiguous or distinct occurrences.
- **FR-017**: Merchant information, transaction data and prompts containing financial data MUST remain local. Errors and logs MUST NOT expose raw financial payloads, notes or credentials.

### Key Entities *(include if feature involves data)*

- **Merchant**: A recognizable business with a canonical name, enabled state, matching entries and an optional default category.
- **Merchant matching entry**: An exact alias or literal substring pattern associated with a merchant, with origin, confirmation and enabled state.
- **Classification preference**: A reusable merchant or description match and category, with origin, confirmation and enabled state.
- **Transaction-specific override**: A user-set category attached to one transaction occurrence and taking precedence over reusable category rules.
- **Rule suggestion**: A proposed AI-originated creation or change, including its review state and any confirmed decisions affected.
- **Evaluation outcome**: The merchant identification, category decision, winning evidence and any conflict or no-match result for an occurrence.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a reference set of at least 100 synthetic descriptions covering case, whitespace, aliases, literal patterns and nonmatches, 100% of expected merchant outcomes and unresolved conflicts are reported correctly and original descriptions remain unchanged.
- **SC-002**: In a reference set covering every precedence level, specificity level and same-rank conflict, 100% of evaluated categories and explanations match the specified precedence; no conflicting category is silently selected.
- **SC-003**: Across at least 20 synthetic AI attempts to modify, disable or conflict with confirmed decisions, 100% of protected decisions remain unchanged until explicit user approval, every conflict is reported for review, and non-conflicting applications remain eligible.
- **SC-004**: In reapplication tests covering at least 50 selected and unselected transactions, 100% of overrides and unselected transactions remain unchanged and every selected conflict is reported.
- **SC-005**: In service-level acceptance tests, 100% of tested user-directed rule creation, override, suggestion approval and rejection actions return inspectable outcomes, including the reason for the selected category or conflict.
- **SC-006**: In completed imports containing new, overlapping and pending-to-booked occurrences, 100% of new occurrences have a completed evaluation or an individually inspectable failed, pending or unknown outcome; when evaluations succeed, 100% have completed outcomes. In all cases, 100% of existing occurrences retain their classifications unless explicitly selected for reapplication. Injected evaluation failures preserve imported data and can be explicitly retried after any unknown outcome is checked.

## Assumptions

- The existing local single-user transaction and classification capabilities, including category, status and source metadata, are prerequisites. This feature adds category rules and merchant identification; it does not define rules for transaction type or budget treatment.
- Rule management, transaction overrides and suggestion review are available through service-level capabilities to application consumers. All user-facing controls for these actions are deferred; explicit user actions are represented by user-directed requests through those capabilities.
- Manual transaction overrides are explicitly designated overrides, separate from ordinary user-sourced or confirmed classification values. This feature protects overrides during rule application; it does not change the existing general classification-update policy.
- Matching uses the bank descriptions available on the occurrence. If multiple linked descriptions produce highest-ranked matches to different merchants, identification remains unresolved.
- Non-conflicting AI-originated rules can be enabled without confirmation, remain provisional and visibly AI-originated, and can be superseded by confirmed rules at the same specificity. User-created rules are confirmed by the user's explicit confirmation.
- A rule-based category is confirmed only when all winning rules are user-confirmed; otherwise it is provisional. No confidence is assigned unless supplied by the existing classification capability.
- Deletion is outside this feature; disabling preserves decisions and their referential context. Changes apply on future evaluations, including new imports, or explicit reapplication, not retroactively by default.
- Merchant aliases and category labels are local to the existing single-user installation. External merchant directories, automatic purchases, analytics and budget calculations are outside scope.
