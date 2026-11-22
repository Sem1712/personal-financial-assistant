# Decision: Personal Bank Transaction Ingestion

- **Slug**: ingestion-mode
- **Decided**: 2026-11-22
- **Verdict**: go
- **Artifacts reviewed**: intake.md, research.md, problem.md, concept.md

## Scorecard

| Criterion | Rating | Justification |
|-----------|--------|---------------|
| Problem validity | adequate | One user has a concrete need to make their Intesa Sanpaolo transactions available to an application whose planned financial analysis depends on transaction data; ingestion does not exist yet. |
| Evidence strength | adequate | The request is direct and the user supplied a real bank XLSX sample whose structure was inspected. Broader demand is limited to this one user's need. |
| Value vs. inaction | adequate | Without ingestion, the user can download a file but cannot use those transactions in the assistant. The manual effort and impact of stale or absent data are not quantified. |
| Feasibility / appetite | adequate | Manual ingestion of the supplied XLSX is a credible medium-appetite concept, though the application is currently only a scaffold and the estimate has low confidence. |
| Strategic fit | strong | A user-downloaded XLSX imported into local storage aligns with the local-first data constraint and the planned transaction-ingestion capability. |
| Risk posture | adequate | The user chose one local XLSX source, removing third-party data-flow and cross-source matching concerns for now. Repeat-import duplicates and pending-to-booked changes remain risks to address in specification. |

## Verdict & Rationale

**Go.** The user has now explicitly chosen manual XLSX ingestion for now, resolving the source-selection and third-party data-flow blocker. The problem is concrete, the supplied workbook grounds the concept, and the recommended single-source approach fits the local-data goal. This is a handoff to specification, not approval to implement unresolved financial-data behavior: import history/frequency, duplicate prevention, pending-to-booked reconciliation, and failure notification need explicit requirements. Evidence supports this individual user's need, not a broader product-demand claim.

## If go — Handoff to `/speckit-specify`

- **Problem**: One Intesa Sanpaolo account's recent and ongoing transactions are not available to the assistant because ingestion is not implemented.
- **Chosen approach**: Option A — user downloads the bank's XLSX export and imports it as the single source, with transaction data retained locally.
- **In scope / out of scope**: One selected account, the supplied XLSX format, persistent local transaction records, booking status and bank categories as classifier suggestions. Automated provider sync, simultaneous multiple sources, other banks, CSV, and other export layouts are out of scope for now.
- **Success metrics**: All eligible transactions from the agreed recent history period are represented accurately; pending status is preserved; imports prevent duplicates; failures are reported; ongoing provider cost is zero. The user expects a few months of initial history and rolling weekly or monthly manual updates.
- **Carried-forward open questions**:
  - How many months of initial history to import and whether updates are weekly or monthly.
  - How repeat imports identify duplicates and reconcile pending transactions that change, disappear, or become booked; ambiguous matches must not silently discard distinct transactions.
  - What failure notification channel is appropriate, especially if the application runs in the background.
  - Whether additional XLSX variations for the selected account need support.
  - How indefinite retention interacts with deletion, backup, or account-disconnection requests.
  - How bank categories should be offered to the decision classifier without treating them as authoritative.

