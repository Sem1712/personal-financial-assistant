# Data Model: Transaction Classification and Context

## Transaction occurrence and source observation

Existing occurrence identity, account, date, exact amount, currency, booking and reconciliation state remain unchanged. Existing linked source observations remain independent evidence, including conflicting bank categories. Enrichment refers to an occurrence by its existing ID; no matching by displayed values and no enrichment copying between different or ambiguous occurrences.

## Classification dimension

At most one current record per `(occurrence_id, dimension)`, where dimension is `transaction_type`, `category` or `budget_treatment`. Missing records represent unclassified dimensions.

| Field | Constraints |
|-------|-------------|
| occurrence_id | Required; references an existing occurrence. |
| dimension | Required; exactly one of the three dimensions. |
| value | Required, nonempty; type is `expense`, `income`, `transfer` or `refund`; budget treatment is `ordinary`, `extraordinary` or `excluded`; category is non-whitespace text. |
| status | Required for a populated dimension: `provisional` or `confirmed`. Missing dimension is reported as `unclassified`. |
| source | Required: `ai`, `rule` or `user`. |
| confidence | Optional finite exact decimal percentage, inclusive 0–100, with at most two decimal places; null means unavailable. Reject greater precision without rounding. |

Database uniqueness, foreign keys and check constraints enforce the invariant in addition to typed boundary validation. An explicit clear removes the dimension and therefore its provenance and confidence; retrieval materializes its value as null, status as `unclassified`, and source and confidence as null. Updating a populated dimension replaces its value and all metadata together. A valid user, AI or rule update can replace any prior value, including a confirmed user value.

For PostgreSQL, use an unconstrained numeric value with explicit finite range and scale checks, or an equivalently exact representation that rejects excess precision before storage. Do not rely on a fixed-scale numeric column that silently rounds inputs.

## Transaction context

At most one context per occurrence, with independent nullable text fields `user_annotation`, `user_explanation` and `ai_explanation`. A null field is absent. A rule explanation is invalid. Text is preserved as supplied and treated as untrusted display data; source is inherent in the field. Updating or clearing one field never changes the others.

## Update and read consistency

A partial update distinguishes omitted fields (unchanged) from explicit null (clear). A dimension set is an indivisible object containing value, status, source and optional confidence. Validate the complete request before writing, lock the occurrence with a five-second lock timeout and commit all requested changes in one transaction. Invalid input, a missing occurrence, timeout or confirmed rollback leaves the prior state unchanged. If a commit outcome cannot be established, report it as unknown and read the current state before retrying. Concurrent updates to the same occurrence serialize; disjoint changes survive and the last committed valid same-field update wins. Cancellation rolls back uncommitted changes and releases resources; an uncertain commit is never presented as a confirmed rollback.

The detail read must return a coherent occurrence, observation and enrichment snapshot, using one statement or a consistent database snapshot; no enrichment row is required for legacy or newly imported occurrences. Migration adds enrichment storage without changing existing observations or backfilling inferred classifications. References to occurrences restrict deletion rather than silently deleting enrichment. A downgrade refuses to discard populated enrichment. Existing currency and integer minor-unit representation is unchanged.

## Relationships and lifecycle

- One occurrence has zero to three populated classification dimensions and zero or one context.
- Source observations remain linked through the existing occurrence-observation relationship and are never edited by enrichment.
- A confirmed unambiguous pending-to-booked reconciliation retains the occurrence's enrichment. No enrichment is copied to or from another occurrence merely because candidate keys match.
- Enrichment persists across repeated imports; no inference is performed at import time.
