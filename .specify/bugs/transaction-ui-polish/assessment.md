# Bug Assessment: Transaction UI polish

- **Slug**: transaction-ui-polish
- **Created**: 2026-11-24
- **Source**: pasted text
- **Verdict**: valid
- **Severity**: medium

## Report

> Every element gets an outline when selected; only inputs and buttons should.
> Placeholders are too invasive and resemble actual input text.
> Transaction details appear at the end of the list; an accordion beneath the
> selected list item would be better.

## Symptom

Programmatically focused headings and statuses receive control-style outlines.
Input hints are visually prominent, and selected evidence is separated from its row.

## Reproduction

1. Navigate to Import or Transactions: the destination heading receives an outline.
2. Compare an empty text field's placeholder with entered text.
3. Open details on a transaction before the last row: details appear after pagination.

## Suspected Code Paths

- `src/personal_financial_assistant/ui/static/styles.css:163`: global focus rule.
- `src/personal_financial_assistant/ui/static/index.html:118`: verbose search hint.
- `src/personal_financial_assistant/ui/static/index.html:166`: detached detail section.
- `src/personal_financial_assistant/ui/static/transactions.js:230`: opening details
  neither moves the panel to the selected row nor toggles an existing selection.

## Root Cause Hypothesis

High confidence: a universal focus selector styles noninteractive focus targets,
Bootstrap's placeholder styling is not customized, and one static detail region
remains after the results and pagination.

## Proposed Remediation

Scope custom focus rings to form controls and keyboard-operated buttons; retain
keyboard visibility for the skip link and focus management without rings on
noninteractive targets. Make hints smaller and lighter than entered text, and
shorten the search hint. Reuse the single details region inside the selected
article, spanning the row's columns, with one open selection and click-to-collapse.
Detach the hidden region before clearing rows so existing references remain valid.
Preserve selected IDs, heading focus, Close/Retry controls, and stale-response guards.

**Files likely to change**:

- `src/personal_financial_assistant/ui/static/styles.css`
- `src/personal_financial_assistant/ui/static/index.html`
- `src/personal_financial_assistant/ui/static/transactions.js`
- `tests/browser/test_navigation.py`
- `tests/browser/test_transactions.py`
- `README.md`
- `specs/003-modernize-ui-ux/contracts/ui-presentation.md`

**Tests to add or update**:

- Focused headings/statuses have no outline; keyboard buttons and inputs retain rings.
- Placeholder color is distinct and lighter, with a smaller font than entered text.
- Details belong to the selected row at desktop/mobile widths, toggle closed, switch
  rows, survive list replacement, and ignore superseded responses.

## Risks & Considerations

- Moving the panel must not destroy DOM references during list replacement.
- Retain focus return, retry identity, safe text rendering, and request-generation guards.
- No APIs, persistence, monetary calculations, migrations, or dependencies change.

## Open Questions

None.
