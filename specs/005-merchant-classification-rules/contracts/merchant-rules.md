# Contract: Merchant Rules and Import Evaluation

The `rules` module exposes typed async operations to trusted local application consumers using a caller-owned async engine or supported pinned connection. Names below describe the required operations; implementation types should follow existing Pydantic and async service conventions. No rule-management HTTP routes or user-facing controls are added. No operation sends financial information or prompts outside the local system.

## Authority and management

- **Automated proposal**: create or edit an unconfirmed merchant entry, default or preference with origin `ai` or `service`, supplying the complete match and category where applicable. AI edits/disables of confirmed entries or indirectly of their merchant return a pending suggestion rather than modifying the protected decision.
- **User-directed management**: create, inspect, edit, enable/disable and explicitly confirm merchants, entries, defaults and preferences. Confirmation is an explicit action, not an AI-supplied boolean. Inspect results include IDs, origin, enabled state, confirmation and revision.
- **Review**: list/inspect pending and stale suggestions and application conflicts; return the affected confirmed entry, proposed change, review snapshot and the outcome that would result under current precedence before a user approves or rejects. Approval is an explicit user-directed operation identifying that snapshot; rejection is explicit too. Recompute the snapshot under the required locks before approval. A changed snapshot or stale revision fails approval without applying the proposed change; callers re-read and re-review.
- **Override**: set, inspect, change or clear the category override for one occurrence. Set/change writes user-sourced confirmed category and the override atomically. Clear removes the override only. Invalid category or unknown occurrence reports an explicit error.

User-directed operations are callable only by the trusted local application code acting on an actual user instruction; model output or an automated agent is not authorized to invoke them as a user. The trusted host preserves actual generation provenance across forwarding and transformations: AI-derived proposals remain AI-originated even if submitted by a classification service. It never trusts a model-provided origin or substitutes the immediate caller for generation origin; unknown provenance is rejected explicitly. This separation is a trust contract for in-process consumers, not authentication against arbitrary code running as the same local user. A future interface must preserve it.

Suggested change approvals alter only the reviewed target and applicable confirmed entries as explicitly presented; they do not authorize unrelated changes. An application approval is limited to one occurrence and one exact typed AI/confirmed pair at the reviewed revisions and evidence revision. When several confirmed entries conflict, all must be approved before that AI entry is eligible for that occurrence. Rejection leaves the protected entry unchanged and blocks that application. Approval removes the block but does not override normal priority; the preview and final outcome must say whether the AI rule would actually win. A change to applicable rules, override, existing category or another snapshot input that changes the reviewed snapshot requires a new review before approval.

## Matching and evaluation

**Input**: one occurrence ID for evaluation or a bounded sequence of explicit occurrence IDs for reapplication. Empty or duplicate IDs in a selection are rejected before writes; unknown IDs return individual not-found results without changing other occurrences. The service uses currently linked source operation/details fields, current enabled rules, scoped approvals and an optional override.

**Output for each occurrence**, in typed form:

```text
occurrence_id
merchant: resolved(merchant_id, winning_entry_refs) | no_match | conflict(candidate_refs)
category: override(value) | applied(value, winning_rule_refs, status) | unchanged(no_rule | conflict)
category_conflict_candidates: rule_refs
blocked_ai_conflicts: conflict_ids and both entry_refs
```

An entry reference contains its kind and ID; IDs alone are not sufficient across rule kinds. The result identifies the winning rule or override and all unresolved conflict candidates. A conflict or no-match is an evaluated outcome, not a storage error. Merchant ambiguity excludes merchant-dependent categories but does not prevent an applicable description preference or override. Apply the exact matching, precedence, safeguard and classification metadata rules in [data-model.md](../data-model.md). Outputs and reviews are inspectable through this service; do not log bank descriptions, categories, notes or proposed payloads.

Operations on selected occurrences are atomic per occurrence, not across the whole selection: return individual success/conflict/error outcomes so one failure does not hide other outcomes. Processing is sequential by default. A caller can explicitly retry failed IDs; unknown commit requires reading the current outcome and category before retrying.

## Import integration and recovery

- Existing `ingest_xlsx` entry points for the CLI and UI continue to import atomically. Every new occurrence, including an unresolved one with no linked observation, gets an evaluation-work record in that same transaction; an existing occurrence linked or reconciled during import does not. Each import gets a stable correlation ID, using the existing UI run ID for UI imports and a generated ID returned to CLI/service callers otherwise.
- After successful import commit, process its new work using the public rules boundary, without holding the import database transaction. A pinned UI connection is reused only after its transaction has ended and remains owned by the UI coordinator. No nested session may commit the outer transaction.
- An additive `ImportResult` evaluation summary reports attempted, completed, failed, pending and unknown counts separately, and per-occurrence identifiers and status through an inspectable service result. Import failure and classification failure are distinct; a completed import with failed evaluation is never described as a failed or rolled-back import.
- Preserve existing CLI counts and UI import-run states. Add sanitized warnings for incomplete/failed evaluation to CLI and existing import status output; expose affected occurrence IDs and individual statuses through the in-process work-inspection operation. Existing UI receives no rule controls, no raw descriptions and no path or payload in warning text.
- Work inspection lists pending, failed and completed records by occurrence or import correlation. An explicit retry targets selected pending/failed work, and rechecks current state before retrying any unknown outcome. Completed automatic work is not replayed merely because the same workbook is imported again. A process interruption after import commit leaves pending work discoverable.
- If an import commit, evaluation commit or work-status write has an unknown outcome, report unknown and require state inspection. If the database is unavailable even for inspection or writing failure state, return a sanitized error and retain the last durable state; never claim an evaluation succeeded.

## Validation and error behavior

Reject missing IDs, invalid/empty matching text or category, unsupported kind/origin, invalid review transitions, stale revisions and duplicate same-merchant entries with a sanitized reason. Do not partially mutate an invalid request. Lock timeout, storage failure with confirmed rollback, and commit-outcome unknown are distinct; unknown requires reading current state before retry. Cancelled operations clean up transactions; no detached work or silent background retry.

The migration must preserve previous observations, enrichment and import-run data on upgrade from `0006`, create no backfill of rule results, and refuse a downgrade that would delete nonempty new feature data. Existing import status and CLI tests must continue passing with additive warning cases.
