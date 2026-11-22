# Problem Definition: Access to Personal Bank Transactions

- **Slug**: ingestion-mode
- **Created**: 2026-11-22
- **Inputs used**: intake.md, research.md, user confirmations and clarifications in this session

## Problem Statement

A user with one Intesa Sanpaolo account needs their recent and ongoing transaction information to be available to their personal financial assistant, but the application has no transaction ingestion today, leaving its planned financial analysis without the user's bank data. The user is open to automated access only if its privacy and provider terms can be verified; otherwise, they can use the bank's Excel export manually.

## Affected Users & Stakeholders

- **Users**: The requester, an individual with one Italian Intesa Sanpaolo account and the application's only intended user for now — currently cannot use their bank transactions in the assistant because ingestion is not implemented. (intake.md; README.md; user clarification)
- **Stakeholders**: The project maintainer — decides acceptable scope and whether third-party financial-data processing fits the local-first project guidance. (AGENTS.md)
- **Stakeholders**: Intesa Sanpaolo and Enable Banking — provide the bank account and confirmed account-access coverage; exact access terms and operational limits remain open. (research.md; user confirmation in this session)

## Goals

- Make one account's transactions from the recent past and on an ongoing basis available to the assistant; the exact lookback period is not yet set. (user clarification)
- Keep recurring service cost free if possible, with a stated maximum of about €2–3 per month. (user clarification)
- Favor maximum privacy; the user has selected the bank's XLSX export for now. (user clarification, 2026-11-22)
- Retain transaction records indefinitely, as requested by the user. (user clarification)
- Preserve transaction booking state; pending transactions should be marked as ongoing/future expenses. (user clarification)
- Keep the bank's categories available as suggestions to the decision API's classifier, not as authoritative classifications. (user clarification)
- When an import or data-access failure occurs, notify the user. (user clarification)

## Non-Goals

- Initiating payments, transfers, purchases, or credit commitments; the assistant is intended to provide advisory guidance only. (README.md; AGENTS.md)
- Supporting banks beyond Intesa Sanpaolo in the initial scope as currently stated. Whether broader bank support is needed remains unconfirmed. (intake.md)
- Supporting multiple users in the initial scope; the user says they will be the only user for now. (user clarification)
- Combining provider sync and Excel imports as simultaneous sources; the user expects to choose one source. (user clarification)
- Supporting Excel layouts other than the provided XLSX for now. (user clarification)
- Deciding a specific ingestion method or implementation design in this problem definition.

## Success Metrics

- **Transaction coverage**: proportion of eligible transactions for the selected account and chosen recent-history window available to the assistant. Baseline: 0 through application ingestion, which is not implemented. Target: all eligible transactions in the agreed period.
- **Transaction accuracy**: dates, amounts, currency, details, and booking state represented correctly. Baseline: no ingestion to measure. Target: no known incorrect values; verify against the bank's source data.
- **Freshness**: delay between a transaction becoming available at the bank and in the assistant. Baseline: no ingestion. Target: weekly or monthly manual imports; the user has not selected between these intervals. (user clarification)
- **User effort**: time spent making a chosen period's transactions available to the assistant. Baseline: manual XLSX download is possible; time not measured. Target: [NEEDS CLARIFICATION: What manual effort is acceptable?]
- **Ongoing cost**: monthly cost of any access service. Baseline: no service selected. Target: free if possible, and no more than about €2–3 per month. (user clarification)
- **Pending-transaction handling**: pending transactions are visibly marked as ongoing/future expenses and remain distinguishable from booked transactions. Baseline: not supported. Target: correct status for all eligible transactions.
- **Failure communication**: access or import failures are brought to the user's attention. Baseline: no ingestion or notification. Target: notify on failure; notification channel and detail remain undecided.
- **Retention**: imported records are retained indefinitely. Baseline: no records stored. Target: no automatic expiry, subject to future explicit retention requirements.

## Cost of Inaction

The user can continue downloading the bank-provided Excel export, but the assistant currently has no implemented way to make those transactions available to its planned analyses. The user's manual effort and the impact of missing or stale transaction data have not been quantified. (intake.md; research.md; README.md)

## Open Questions

- The user has selected manual XLSX ingestion for now; automated provider access is deferred.
- [NEEDS CLARIFICATION: How many months of initial transaction history are needed? The user expects a few months followed by rolling imports.]
- [NEEDS CLARIFICATION: Should manual imports happen weekly or monthly?]
- [NEEDS CLARIFICATION: How should pending transactions that change, disappear, or become booked be reconciled and shown as ongoing/future expenses?]
- [NEEDS CLARIFICATION: What notification channel should be used for import failures?]
- [NEEDS CLARIFICATION: Will the application be launched manually or run in the background?]
- [NEEDS CLARIFICATION: How should the bank's Italian category be supplied as a suggestion to the decision API classifier, and how should a conflicting classifier result be handled?]
- [NEEDS CLARIFICATION: Are there meaningful XLSX variations for the selected account that must be supported beyond the supplied example?]
- [NEEDS CLARIFICATION: How should indefinite retention interact with future deletion, backup, or account-disconnection requests?]
