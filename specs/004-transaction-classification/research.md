# Research: Transaction Classification and Context

## Separate enrichment from bank evidence

**Decision**: Attach current enrichment to transaction occurrences, not to source observations. Keep the existing observation category and its filter semantics unchanged. An absence of enrichment yields explicit unclassified values, not a value derived from signs or bank suggestions.

**Rationale**: The transaction detail service already returns occurrences with their explicitly linked observations, which can disagree. Keeping enrichment separate protects the imported evidence and preserves occurrence identity and existing list behavior.

**Alternatives considered**: Overwriting the bank category loses evidence; storing enrichment on observations duplicates or fragments a classification across overlapping imports.

## Independent values and provenance

**Decision**: Store each populated dimension with its own status, source and optional exact decimal percentage with at most two decimal places. Reject excess precision rather than rounding. Store a user annotation, a user explanation and an AI explanation separately.

**Rationale**: The clarifications permit different sources and statuses for type, category and budget treatment, permit user and AI explanations to coexist, and set confidence precision. Exact decimal percentages avoid rounding a supplied confidence.

**Alternatives considered**: One shared status/source would misrepresent mixed provenance. A fixed category enumeration would reject legitimate categories. Generating classifications or explanations now would exceed the feature scope.

## Controlled updates and concurrency

**Decision**: Expose an async, typed in-process transaction-enrichment update operation, not a new browser editing endpoint. Validate the entire partial update first, then lock the occurrence row within a database transaction and apply only supplied fields. Serialize writers to the same occurrence. For the same field, the last successfully committed valid update wins, including an AI/rule update replacing a confirmed user value; disjoint updates retain one another. Use a five-second database lock timeout; report validation, missing occurrence, lock timeout and storage failures with confirmed rollback explicitly. If a commit outcome cannot be established, report unknown outcome and require a read before retrying instead of claiming rollback.

**Rationale**: The specification permits automated replacement, while unrelated dimensions and context must remain unchanged. A shared occurrence row exists before enrichment, so locking it also serializes initial concurrent writes without needing pre-created enrichment rows. Ingestion uses an import-wide advisory lock that enrichment writers do not take; its occurrence updates still interact with the row lock. Deadlocks and timeouts must surface without partial writes.

**Alternatives considered**: Full replacement of a stale snapshot loses unrelated changes. Unconditional upserts without a common lock can interleave multi-field updates. Rejecting automatic replacements contradicts the clarified scope. A versioning/conflict interface would add an unrequested user-facing policy.

## Detail-view presentation

**Decision**: Extend the existing transaction-detail response and detail panel only. Label dimensions, statuses, sources, confidence, annotations and explanations separately from bank observations; show missing values explicitly and define excluded treatment as intended exclusion from future budgets. Render text with DOM text APIs and retain loading, retry, keyboard and empty states.

**Rationale**: The existing `/api/transactions/detail` flow already retrieves the relevant observation evidence and uses `textContent` for untrusted imported text. Existing list and bank-category filters must not change.

**Alternatives considered**: A new detail endpoint duplicates the existing flow; list presentation or editing controls violate the clarified scope.

## Validation strategy

**Decision**: Exercise model validation and update behavior with deterministic unit tests; use real PostgreSQL testcontainers for migration, persistence, rollback, concurrent updates, and ingestion/reconciliation contracts. Extend route and browser tests with synthetic values and text-injection cases. Run the existing uv quality gates, and report missing infrastructure or skipped tests rather than claiming success.

**Rationale**: The constitution requires real PostgreSQL and migration checks for both clean and existing databases. The current UI, transaction-query and ingestion suites already provide suitable patterns.

**Alternatives considered**: SQLite substitutes cannot establish PostgreSQL constraints or locking semantics; mocked browser responses alone cannot prove persistence and migration behavior.

## Migration and occurrence lifecycle

**Decision**: Add a revision after the current `0004` head, with restrictive references from enrichment to occurrences. A downgrade must refuse to discard populated enrichment. Reconciliation must keep enrichment with the existing occurrence; no new occurrence merge or deletion behavior is introduced.

**Rationale**: Existing import reconciliation preserves occurrence identities, and ingestion's advisory lock protects imports only. Existing migration conventions guard downgrades that would discard unsupported data. Restrictive foreign keys prevent accidental silent loss if a future deletion path is introduced.

**Alternatives considered**: Cascading deletion would silently discard user context; transferring enrichment based on matching keys could attach it to the wrong real-world transaction.
