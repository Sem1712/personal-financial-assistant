# Bug Fix: Transaction UI polish

- **Slug**: transaction-ui-polish
- **Fixed**: 2026-11-24
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

Noninteractive focus targets no longer receive outlines. Placeholder hints are
smaller and lighter, and transaction evidence expands inside the selected row.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/personal_financial_assistant/ui/static/styles.css` | Modified | Scoped focus selectors retain Bootstrap-specific overrides; 14px hints versus 16px input text; full-width detail region. |
| `src/personal_financial_assistant/ui/static/index.html` | Modified | Shorter search hint and accordion styling hook. |
| `src/personal_financial_assistant/ui/static/transactions.js` | Modified | Toggle selection, move panel into selected row, park hidden panel outside results before replacement. |
| `tests/browser/test_navigation.py` | Added test | Focus outlines and placeholder distinction. |
| `tests/browser/test_transactions.py` | Added/extended tests | Responsive accordion position, toggle, focus, row switching, replacement, and pending-response invalidation. |
| `README.md` | Modified | Describes hints, focus rings, and accordion behavior. |
| `specs/003-modernize-ui-ux/contracts/ui-presentation.md` | Modified | Specifies changed presentation and interaction contracts. |

## Local Verification

- `uv run --locked ruff check`: passed.
- `uv run --locked ruff format --check`: passed.
- `uv run --locked pyright`: zero errors or warnings.
- `uv run --locked pytest tests/unit/ui -q`: 51 passed.
- `git diff --check`: passed.
- Targeted Playwright regression tests could not launch Chromium because
  `libnspr4.so` is missing. No browser or system packages were installed; these
  tests are not reported as passing.
- Integrated-browser checks with controlled synthetic data passed at 320px and
  1440px: panel beneath selected summary and before next row, no horizontal
  overflow, toggle closure, focus return, and one expanded row.
- Computed styles confirmed no heading/status outline, 3px input and keyboard
  button outlines, 14px placeholder text in `rgb(108, 122, 141)` versus 16px
  entered text in `rgb(32, 48, 71)`.
- Full application flow with controlled in-page fetch responses passed row
  switching, stale-response rejection, close focus, paging invalidation, selected
  identity on failure/retry, and navigation/reentry.
- PostgreSQL integration and full release gates were not run: no persistence,
  backend, migrations, or monetary behavior changed.

## Deviations from Assessment

No behavioral deviations. Browser validation caught Bootstrap selector specificity
overriding an initial form-control ring; retaining explicit Bootstrap class selectors
resolved this before final verification.

## Follow-ups

Run the optional browser regressions when the existing browser environment has
its required system libraries.
