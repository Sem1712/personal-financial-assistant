# Contract: Modernized Local UI Presentation

**Scope**: [spec.md](../spec.md), FR-001 through FR-016.
The existing [local UI HTTP contract](../../002-financial-assistant-ui/contracts/local-ui.md)
remains unchanged. This contract defines presentation additions, not new endpoints.

## 1. Assets and application shell

- Serve `/static/bootstrap.min.css` before `/static/styles.css` from the current
  application. Package the full Bootstrap license with the stylesheet.
- Use a fixed dark theme via root `data-bs-theme="dark"` and shared palette
  variables. Native controls, surfaces, hints, focus rings, selected navigation,
  disabled actions, and semantic status colors must remain readable in dark mode.
  Normal enabled text and placeholder hints must meet 4.5:1 contrast against their
  surfaces; transaction borders use the signed-amount rules below.
  Theme changes must not alter existing interactions or add theme selection/storage.
- No runtime CDN, remote font/icon, inline style/script, analytics, or telemetry.
- Preserve Host/Origin/token enforcement, no-store responses, restrictive CSP,
  safe-text rendering, and absence of sensitive URL/log values.
- Override embedded select/validation images without broadening CSP. Ensure
  `[hidden]` takes precedence over Bootstrap display utilities.
- Keep view IDs `chat`, `import`, and `transactions`. Preserve existing control IDs
  and names where practical so behavior does not depend on a parallel rewritten UI.
- Navigation uses buttons for the existing in-page action, not simulated tabs without
  their keyboard contract. The current button carries `aria-current="page"` and
  a visible selected treatment; noncurrent buttons do not claim selection.
- A skip-to-main link and destination heading support keyboard orientation.
- Chat/reports remain explicitly unavailable with no message/report submission.

## 2. Navigation and focus

- Guard navigation using the existing fresh import-status check. Do not change
  selected styling or expose another view before that check succeeds.
- Blocked navigation retains Import and announces the safe reason.
- Focus the destination heading only on an actual view change, including a forced
  recovery transition from another area. Repeated Import polls must not steal focus.
- Hidden areas and controls are not keyboard-focusable or announced as visible.
- Custom focus rings apply to form controls and keyboard-focused buttons, not
  programmatically focused headings or statuses. Keep the keyboard skip link visible.
- Input placeholders are smaller, lighter, italic hints; examples are explicitly
  prefixed with "e.g." so they cannot be mistaken for entered values.
- All headings, controls, statuses, and long content remain usable at tested widths.
  No fixed-height clipping or page-level horizontal scroll.

## 3. Import form and status

- Group the labeled Local folder input, local-folder help, and Start import action.
  Recovery actions are separate and remain visible whenever existing state allows.
- Keep existing running locks and the unknown-outcome warning; no estimated progress.
- Display all eight count labels and unresolved explanation. Keep recovered IDs and
  per-run results distinct, with existing dismissal/resolution safeguards.
- Use a live status region for changed messages; stable polling does not rewrite
  identical announced text. Text conveys every state independently of color.
- Invalid input retains the typed path, sets `aria-invalid`, and associates explanatory
  text with the field. Clear only the applicable invalid association after correction
  or a subsequent valid attempt, without erasing an unrelated recovery warning.
- Status kind comes from workflow fields/safe notice, not translated or English text.
- A retained folder rejection stays invalid-input; a previous completed run is
  labeled as an earlier outcome rather than making the rejected attempt look successful.
- Before disabling or hiding a focused folder/action control, move focus to the
  visible import status. Leave focus on unaffected controls alone, including when
  the user moves elsewhere while a recovery response is pending. Native invalid
  folder handling continues to focus the field.

## 4. Filters, list, and paging

- Put the filter form in a native, keyboard-operable accordion, collapsed on initial
  page load. Opening/closing preserves drafts and applied criteria and does not fetch
  results. Applied-filter summary stays visible outside the accordion.
- Preserve labels and rules for From date, To date, Booking status, Description,
  and Bank-suggested category. Amount bounds are nonnegative absolute EUR amounts,
  inclusive and exact to cents, with zero as the lowest allowed value; either bound
  may be empty. They match both signs. Transaction type selects All (including zero),
  Withdrawals (strictly negative), or Deposits (strictly positive), combined with
  other criteria. Negative bounds, excessive precision, and inverted ranges fail
  explicitly. Support the full signed-64-bit magnitude, including 2^63 cents.
- At medium and wider widths, dates/status occupy the first row, transaction type
  and the two amount bounds share the second row with aligned controls, and
  description/category follow. Stack controls in the same order on narrow screens.
- Apply filters remains explicit. Display an applied-filter summary separate from
  editable drafts; it changes with the validated query, not typing.
- Invalid ranges preserve entries, identify applicable inputs, and remove misleading
  current results. No search request is issued for invalid input.
- Date fields use the existing canonical four-digit ISO-date range, 0001 through 9999;
  unsupported years retain their values and receive field-associated feedback.
- Clear filters resets criteria/page state and retrieves the unfiltered list.
- One semantic article represents one occurrence. Wide rows prioritize recorded
  operation text, then date, amount, and a single chevron Details toggle; narrow
  rows stack labeled values. Distinct linked operations are shown without selecting
  a preferred source; missing operation text is explicitly unavailable.
  Show sorted distinct linked source details directly under operations, as smaller
  muted single-line text with an ellipsis when overflowing, without per-row requests.
  Missing details are explicitly unavailable. Full text remains in expanded details.
  Preserve separate source observations in the expanded evidence panel.
  Never duplicate interactive desktop/mobile copies.
- Positive amounts have a distinct green 2px card border unless Deposits is the
  applied filter, in which case they remain neutral. This persists during paging,
  ignores unapplied selector changes, and resets when applied criteria change.
  EUR expenses of 99.95 or
  more (signed minor units <= -9995) have a red 2px border, using exact integer
  comparison. Other negative and zero amounts retain neutral borders; no currency
  conversion is inferred. Signed amount/currency text remains the primary evidence.
- Booking status, reconciliation, and ongoing-expense information remain in details,
  not the primary row summary.
- Keep exact signed amount/currency text, unknown/unresolved evidence, and the
  existing pending-debit ongoing-expense rule; pending credits are not expenses.
- Centered First/Previous/Next pagination appears above and below results. Controls
  are always visible and disabled during loading or at unavailable boundaries.
  First is separated by a gap from the connected Previous/Next pair. Disabled buttons
  have muted text, gray backgrounds, and a not-allowed cursor.
  First resets cursor history without clearing applied filters. The default page
  size is 100 records. Numbered page links are not required.
- Top pagination keeps the current position, where page height allows, if already
  fully visible. Bottom pagination always scrolls smoothly to the top pagination
  bar, even when it was already visible. Reduced-motion preferences use an instant
  jump instead. Keyboard focus returns to
  the corresponding top control, or the result status at a boundary, without another
  position change or stealing focus after user movement.
- While paging, previous rows remain dimmed, inert, and marked busy until replaced
  atomically. They are not presented as completed current results; this preserves
  layout height during retrieval. Failures clear them and report the error.
- User-initiated paging/retries keep focus at a stable status target while loading.
  Paging restores the corresponding top control; retries restore an available
  initiating control, or use the category field after successful category retry.
  Do not move focus back if the user has moved elsewhere.
- Distinguish loading, no history, no matches, list failure, category failure, and
  details failure. Keep applicable Import, Clear filters, and retry actions accessible.
- Retain the warning that export records are not a live balance or complete history.

## 5. Inline detail inspection

- Details selects the actual occurrence ID and shows date and exact amount/
  currency in an accordion beneath that occurrence's summary, inside its article,
  with a stable focusable heading. Only one occurrence is expanded at a time.
  Focus stays on the toggle when expanding; there is no separate Close button.
- Activating the expanded occurrence's details button collapses it and retains
  focus on that button. Opening another occurrence moves the same detail region.
- Linked observations remain separate; missing values are unavailable and bank
  categories remain suggestions. Insert source text through text nodes.
- A retrieval failure retains selected context and offers Retry details for that ID.
- Collapsing details invalidates the response and retains focus on the toggle.
- Paging, applying/clearing filters, or navigation refresh clears stale details.
  A superseded response cannot reopen or replace the current selection.

## 6. Unchanged transport and persistence

Transaction search/detail items additionally expose `operations`, a sorted list of
distinct non-null operation texts from explicitly linked source observations.
Search aggregates this evidence within the existing page query, without per-row
requests, extra occurrence rows, or persistence changes.

Continue using:

- `POST /api/imports`
- `GET /api/imports/current`
- `POST /api/imports/status`
- `POST /api/imports/resolve`
- `POST /api/transactions/search`
- `POST /api/transactions/categories`
- `POST /api/transactions/detail`

Preserve existing request bodies, token headers, error statuses, deadlines, recovery
semantics, pagination, and exact financial values. No new schema, storage keys,
backend endpoints, provider requests, or external integrations.

## 7. Verification evidence

Playground checks and maintainer usability approval are sufficient UI evidence under
the [scoped exception](../spec.md#scoped-verification-exception-approved-2026-11-24).
Browser/E2E tests remain optional. Keep local-resource, safe-text, and unchanged
security contracts; applicable non-browser asset/security tests remain required.

No browser installation, exhaustive acceptance matrix, participant study, or formal
accessibility certification is required. See [quickstart.md](../quickstart.md) for
playground examples and required non-browser engineering checks.
