# Concept: Personal Bank Transaction Ingestion

- **Slug**: ingestion-mode
- **Created**: 2026-11-22
- **Recommended option**: A — Manual Intesa XLSX ingestion
- **Inputs**: [problem.md](./problem.md), [intake.md](./intake.md), [research.md](./research.md), [project constitution](../../../AGENTS.md)

## Options

### Option A — Manual Intesa XLSX ingestion

- **Sketch**: The user periodically downloads the existing bank export and makes it available to the assistant. Transactions for the selected account become persistent local records, including booking status and bank-provided categories as classifier suggestions; failures are reported. This is the smallest proposed addition to the current application, not a combination of manual and provider sources.
- **Appetite**: medium (weeks) as a provisional budget, not an estimate. Confidence is low: the project does not yet have its planned database or ingestion capability.
- **Trade-offs**: Uses the supplied export and avoids a new open-banking provider, aligning with the user's privacy preference and weekly-to-monthly manual cadence. It requires recurring user effort and does not provide daily automated freshness. A single observed workbook does not prove that all exports have identical content or layout.
- **Rabbit holes**: Repeated overlapping exports have no visible transaction ID; genuinely distinct transactions may otherwise be mistaken for duplicates. Pending transactions can change or become booked. Correctness requires handling uncertainty without silently dropping records, as well as respecting indefinite retention and reporting failures.

### Option B — Automated access through Enable Banking

- **Sketch**: The user authorizes access to the selected Intesa Sanpaolo account and the assistant obtains transaction information periodically, retaining local records and reporting failures. The provider would be the single transaction source, not a simultaneous companion to XLSX ingestion.
- **Appetite**: medium (weeks) as a provisional budget, not an estimate. Confidence is low: provider conditions, project infrastructure, and operational behavior remain unverified.
- **Trade-offs**: Better matches the user's preference for daily or weekly automation and less manual effort. It depends on third-party availability, consent renewal, the provider's actual coverage and terms for this account, and the user's acceptance of its privacy practices. The user confirmed Intesa support and considers the provider trustworthy, but the current personal-use terms and data handling were not independently verified in the research.
- **Rabbit holes**: Consent and renewal, provider or bank outages, transaction history and pending-status coverage, deployment mode, and any limits on refreshes. The [project constitution](../../../AGENTS.md) requires bank data to remain within the local system; any conflict involving third-party processing must be explicitly resolved under its governance rules before implementation.

### Option C — Do nothing

- **Sketch**: Continue using the bank's own downloaded files outside the assistant and defer making transactions available to the application.
- **Appetite**: small (days), as an upper-bound assessment budget rather than an implementation estimate; no ingestion is built.
- **Trade-offs**: Avoids development, provider cost, and new access arrangements, but does not meet the goal of having transactions available to the assistant or enable its planned analysis of them.
- **Rabbit holes**: Repeated manual handling outside the application may still take time, but the effort and impact have not been measured.

## Recommendation

Recommend **Option A — Manual Intesa XLSX ingestion**. The user selected this path for now, has supplied an example export, and accepts weekly or monthly manual updates. It keeps transaction data local after the user downloads the file and avoids relying on unverified third-party processing terms. Option B is deferred unless the user later reopens the provider choice.

The initial lookback period, import frequency, duplicate handling, pending-to-booked reconciliation, and failure notification channel remain specification questions. They do not change the selected source, but must be resolved before implementation. Appetite is a provisional scope budget with low confidence, not a delivery promise.

## Out of Scope (for the recommended option)

- Automatic provider synchronization or simultaneous provider and XLSX ingestion; Enable Banking is deferred for now.
- Banks beyond Intesa Sanpaolo, additional users, CSV, and other export layouts unless scope is later changed.
- Payments, transfers, purchases, and credit commitments.
- A new classifier or financial-guidance feature; the bank category is only a potential input suggestion.
- A separate transaction-display interface: persistent records are requested, while a visible list was not requested.

## Assumptions to Validate

- The supplied XLSX is representative of the selected account's recurring exports and contains enough recent history; the exact lookback period still needs agreement.
- Weekly or monthly manual downloads are acceptable in practice, and available exports can meet the desired transaction coverage and freshness.
- Duplicate prevention and pending-to-booked reconciliation can be made reliable enough without a visible transaction ID; ambiguous cases can be surfaced rather than silently discarded.
- Failure notification, indefinite retention, and any later deletion or backup expectations can be accommodated in the eventual run mode, which is not yet chosen.
