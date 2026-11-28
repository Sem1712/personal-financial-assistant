# Research: Merchant Identification and Classification Rules

## Existing boundaries and data

- **Decision**: Add a public `rules` module and use existing transaction occurrence and classification records. Retain `transactions.update_enrichment` as the general-purpose update boundary; extract a focused shared occurrence/category operation where needed for atomic rules updates.
- **Rationale**: `transactions/enrichment.py` already validates category/source/status and locks the occurrence; its public API permits automated replacement of ordinary confirmed classifications. Rule lifecycle is new domain behavior and must not rely on private transaction helpers or redefine all existing updates.
- **Alternatives considered**: Put all rule lifecycle in ingestion or transaction reading; rejected because it couples independent responsibilities. Globally prohibit automatic replacement; rejected because the prior feature explicitly permits it.

## Import commit, retry and reporting

- **Decision**: Insert one durable evaluation work item per newly created occurrence within the existing import transaction, then evaluate after commit. Retain per-occurrence outcomes and explicitly retry failed or pending items; no automatic reclassification of linked existing occurrences.
- **Rationale**: `ingestion/service.py` reconciles an entire batch in `session_scope` and returns only after commit; the CLI and UI both call it, the latter with a pinned connection. A same-transaction classifier failure would roll back source data, while an in-memory list alone loses work if the process stops after commit. A work item for an unresolved occurrence with no linked observations still produces an explicit no-match.
- **Alternatives considered**: Evaluate inside the import transaction; violates the chosen failure policy. Fire-and-forget background tasks or a transient ID list; cannot reliably report interrupted work. Re-evaluate every reimport; contradicts the spec.

## Matching and precedence

- **Decision**: Case-fold and collapse/trim whitespace on each linked `operation` and `details` separately; compare exact aliases or literal substrings. Evaluate AI-versus-confirmed conflicts for the actual occurrence before ordinary specificity and precedence; report all matches relevant to conflicts and ties.
- **Rationale**: These are the existing source-description fields and may disagree across observations. Independent matching does not fabricate a combined bank description. Literal matching follows clarification and avoids regex execution risks.
- **Alternatives considered**: Bank category as a merchant hint, concatenated descriptions, regular expressions or arbitrary first-match wins; these invent evidence or violate the spec.

## Review authority and scoped approvals

- **Decision**: Separate trusted user-directed operations from automated proposal operations. Preserve generation provenance across forwarding, use kind-qualified rule references, and scope an application approval to the occurrence, conflicting typed entries and their revisions, plus linked evidence. Recompute the complete review snapshot under locks before approval; changing referenced rules or linked evidence invalidates an existing approval.
- **Rationale**: An agent or forwarding classification service must not re-label model output as deterministic, and an approval for one conflict must not silently authorize a later different conflict. Different rule tables can use the same local ID. A new applicable rule, changed override or changed current category can also invalidate a previously shown result even when the reviewed pair is unchanged. There is no existing agent or authentication service; trusted local application code owns provenance, not a security boundary against arbitrary local code.
- **Alternatives considered**: Trust a caller-supplied `confirmed=true`, infer origin from the immediate caller, or validate only the originally reviewed IDs and revisions; each permits misattribution or stale approval. Global approval for all matching transactions conflicts with the user's per-transaction choice.

## Concurrency and snapshots

- **Decision**: A single persisted rules-configuration row serializes all rule mutations, user reviews and evaluations; acquire it before the target occurrence row. Occurrence-level locks also serialize overrides, enrichment writes and import changes to linked observations. Use bounded lock waits and re-check expected revisions; no network calls while locks are held.
- **Rationale**: The application is single-user with no throughput requirement, and `update_enrichment` already locks the occurrence with a five-second timeout. A config lock prevents a rule being confirmed concurrently after an evaluator read it; the occurrence lock prevents stale evidence, overrides or concurrent category writes.
- **Alternatives considered**: Per-rule locks alone; cannot safely lock future matching rules or detect all concurrent inserts. Optimistic reads without a validation lock; leaves a gap between conflict detection and commit.

## Result recovery and failure semantics

- **Decision**: Keep durable work states and latest outcome separate from import success. Claim, evaluate and mark success in one transaction per occurrence; a failed/unknown commit is reported distinctly and state is read before retry. A crash leaves pending work discoverable; do not silently retry or mark it successful.
- **Rationale**: The existing UI import coordinator distinguishes `unknown` from failed and protects a pinned connection. The classification phase must preserve this honesty while keeping a committed import.
- **Alternatives considered**: Treat a classification problem as an import failure or discard per-occurrence results; misrepresents committed data or makes failures impossible to recover.

## Migration and quality gates

- **Decision**: Add an Alembic revision after `0006_category_whitespace`; constrain ownership, allowed states, nonempty text and reference integrity. Guard downgrade if it would discard rule, review, override or work data. Test empty and populated `0006` schemas with PostgreSQL testcontainers.
- **Rationale**: Runtime table creation and SQLite substitution are forbidden by the constitution, and the existing schema already contains user annotations and classification provenance that must survive.
- **Alternatives considered**: Reuse the generic classifications table for all rules or drop feature data on downgrade; obscures distinct lifecycles or loses user decisions.
