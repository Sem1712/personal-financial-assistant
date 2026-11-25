# Data Model: Modernize UI and UX

This feature adds transient presentation state, not database entities. The existing
[UI data model](../002-financial-assistant-ui/data-model.md) and
[local HTTP contract](../002-financial-assistant-ui/contracts/local-ui.md) remain
authoritative for persistence, filtering, and import semantics. No Alembic migration.

## Application area

**Fields**: selected area (`chat`, `import`, `transactions`), navigation-locked flag,
visible explanatory status.

**Rules**:

- Chat is initially selected unless import recovery requires Import.
- Selection changes only after the existing import-status guard allows it.
- Selected styling and `aria-current` agree with the actually visible area.
- Real area changes focus the destination heading; same-area polling does not.
- Navigate only among the three known view roots, not arbitrary nested sections.

## Import presentation

**Inputs**: Existing current/tracked runs, request correlation, pending/completed/
missing IDs, storage availability, start/conflict flags, and persistent safe notice.

**Derived fields**: visible status message and presentation kind, existing counts,
recovered-outcome list, input-error association, and enabled/hidden recovery actions.

**Kinds**: informational, running, successful, no-files, failed, unknown, invalid-input,
and storage-unavailable. These are UI classifications, not new persisted run states.
The current run's `state` remains `running`, `succeeded`, `no_files`, `failed`, or `unknown`.

**Rules**:

- Interpret structured state; no message-string classification or fabricated progress.
- A successful run with unresolved observations retains its warning alongside counts.
- Each recovered run has its own ID, kind, and counts; do not summarize mixed
  recovered outcomes as blanket success.
- Validation retains the folder value and safe notice across polls.
- Storage failure, missing tracking, and unknown status retain existing locking rules.
- Do not change opaque-ID storage keys, request correlation, resolution, or dismissal.
- Updating unchanged status text must not repeat an assistive-technology announcement.

## Transaction browsing context

**Fields**:

- Draft values: current form inputs, not necessarily submitted.
- Applied filters: last validated filter object used for the current query.
- Query state: loading, populated, empty-history, no-matches, invalid-input, or failed.
- Cursor state: current cursor, previous-cursor stack, next cursor.
- Category state: loading, available, or unavailable with retry.
- Validation association: affected field IDs and safe explanatory message.
- Response generation: existing query/detail sequence counters.

**Rules**:

- Apply validates and copies drafts to applied filters, resets pagination, clears
  details, and requests data. Typing alone does not change the query or its summary.
- Preserve inclusive ranges, exact nonnegative EUR cent parsing against absolute
  amounts from 0 through 2^63, all-criteria combination,
  category/no-category matching, and separate identical-looking occurrences.
- Direction independently selects All (including zero), strictly negative
  Withdrawals, or strictly positive Deposits; it participates in cursor fingerprints.
- Invalid Apply preserves drafts, clears misleading results/details and page controls,
  and identifies the fields needing correction. It does not issue a search.
- Clear resets drafts/applied filters and cursor state and retrieves unfiltered data.
- Pagination changes only cursors and uses the same applied filters.
- Failures are explicit states, never successful empty lists; category failures leave
  unrelated filters usable. Old response generations cannot replace current content.
- Applied-filter summary is rendered locally as text, never persisted or put in a URL.
- Native filter accordion starts collapsed; toggling only changes presentation,
  preserving drafts, applied criteria, and the visible summary without requesting data.

## Selected transaction details

**Fields**: opaque occurrence ID, date, exact amount string and currency, request state
(loading, ready, failed), linked observations, initiating control reference.

**Relationships**: Selection belongs to one occurrence in the current list.
Observations retain their existing operation, details, bank-suggested category,
and source booking status; missing/conflicting evidence remains explicit.
Search items expose sorted distinct linked operation texts for the primary row,
and distinct non-null source details beneath them as smaller single-line muted text,
with an ellipsis on overflow and full text in expanded observations. Empty detail
arrays explicitly mean unavailable text. No extra per-row requests or persistence
changes are required. No preferred observation is chosen. Positive amounts receive a presentation-only
green border unless the applied direction is Deposits, when their borders are neutral.
Draft changes do not affect current results; paging retains the applied rule.
EUR expenses with exact signed minor units <= -9995 receive a red
border; other negative and zero amounts stay neutral, without currency conversion.
Booking and reconciliation states remain in details.

**Rules and transitions**:

1. Details establishes selected ID/context and retains focus on its chevron toggle.
2. Current-generation success displays observations; failure retains context and retry.
3. Retry fetches the same selected ID; closing invalidates its pending response.
4. The same toggle clears selection and retains focus; there is no separate Close button.
5. Filter/page/navigation refresh invalidates selection and pending details; focus
   follows the action or destination rather than an obsolete initiating element.

Exact amount formatting remains string based; IDs are not converted to floating point.
Date/amount/currency identify context for the user but never replace occurrence identity.
