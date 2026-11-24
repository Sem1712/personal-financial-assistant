# Contract: Local Financial Assistant UI

## Boundary and common rules

The new `personal-financial-assistant serve-ui` command serves `http://127.0.0.1:8765/` on the same host. It must not bind to a non-loopback address. Existing `ingest-xlsx` invocation and results remain unchanged.

All UI assets are served locally. Validate the exact Host and port and reject cross-origin requests. Embed a server-generated, unpredictable per-process token in the same-origin HTML bootstrap and supply it as `X-PFA-Token` on every `/api/` request; do not persist the token in browser storage. Reject foreign Origins and require the exact Origin on state-changing requests; reject unsafe cross-site Fetch Metadata when supplied. No permissive CORS; unsafe endpoints accept JSON only. GET/HEAD never change state. Render untrusted bank text as text, not markup. Responses containing UI or data use `Cache-Control: no-store`; apply a restrictive CSP and frame protection.

Do not include folder paths, transaction text, categories, amounts, tokens, credentials or account details in URLs, access logs, exception logs or error responses. Disable default web-server access logs and sanitize framework validation errors rather than echoing submitted values. Financial data is displayed only in the local UI. Status errors use JSON `{ "error": { "code": "...", "message": "..." } }` with an allowlisted safe code and sanitized message; validation returns 422, UI import conflict 409, security rejection 403, and unavailable storage or coordinator 503. Unexpected errors return sanitized 500 and a non-sensitive diagnostic. Never map retrieval or import errors to successful empty results.

## Navigation and user-visible states

- Start on a chat placeholder that clearly states chat and reports are unavailable. Do not accept messages or claim reports exist. Provide links to import and transactions.
- Import accepts a local folder path and a start action. Each open tab polls for import status, and checks it again before navigation away from Import. While a UI run is running, present its status, prevent another UI start, and block navigation within the application with an explanation. On completion, restore navigation and show the result and all relevant counts. The browser retains only opaque request IDs in local storage across reloads and tab closure; if storage is unavailable, starting an import is disabled with an explanation. Run IDs remain until a subsequent import is initiated, so reopening can recover the outcome; unresolved IDs block new starts. A run is attributed to a pending request only when its ID matches. If the request's outcome cannot be established, show `unknown`, never fabricated success or failure. Folder-validation feedback remains visible during polling.
- When several tracked IDs remain, show each confirmed outcome and its counts with its ID, including during another import or an unresolved outcome. Preserve these outcomes across subsequent starts until the user explicitly dismisses them.
- An unrecorded request may be explicitly resolved without resubmitting it. The service must first durably close that ID against any delayed start; retain the outcome as unknown, advise checking transactions, and unlock only when no import remains active. Resolution is unavailable if exclusive ownership or safe cleanup cannot be established.
- Transactions show one row per occurrence, with date, exact signed EUR amount, booking status including unknown, reconciliation state, and ongoing-expense status where appropriate. Detail shows linked observation values and clearly labeled bank category suggestions.
- Provide date, status, description, category, no-recorded-category and signed amount filters, combine them, clear them and page the result. Invalid ranges show an actionable validation error. Distinguish no history, no matches and retrieval failure; offer import, clear or retry respectively.
- Make controls keyboard accessible, associate visible labels, and announce running/completed/error states. State that exports do not constitute a live balance or complete history.

## HTTP interface

These are local application contracts, not a remotely supported public API. Every request has the protections above; sensitive filter values are JSON bodies, never query parameters.

### `POST /api/imports`

Request: `{ "input_dir": "/absolute/or/relative/local/folder", "request_id": "<optional UUID>" }`. Reject blank/NUL paths and malformed request IDs; resolve relative paths against the process working directory, without returning or logging the path. Explicitly initiate one import. When supplied, the request ID becomes the run ID; otherwise the server generates one. This ID permits correlation after a lost response and cannot be reused to start a second import.

Response: `202` with `{ "id": "<opaque UUID>", "state": "running" }` after the durable run record is committed. A UI run already active returns 409. An already recorded ID returns 409 with code `import_request_closed`; look up its outcome rather than assuming rejection. Invalid input returns 422. Coordinator, configuration, or storage failure returns a safe 503 or appropriate sanitized error, and must not schedule an unrecorded import. A 503 with code `import_not_started` confirms rejection before a run could be recorded; `coordinator_unavailable` can indicate an indeterminate outcome and must not be treated as a confirmed rejection. Storage unavailability takes precedence over checking whether the folder is empty; it is not reported as `no_files`.

### `GET /api/imports/current`

Return `{ "run": null }` when no UI run exists; otherwise `run` has `id`, `state`, `started_at`, nullable `finished_at`, nullable `counts`, and nullable `error`. For `succeeded`/`no_files`, `counts` contains `files_seen`, `files_processed`, `files_unchanged`, `rows_read`, `transactions_added`, `transactions_updated`, `observations_unchanged`, and `unresolved_observations`. A `failed` run has a sanitized error code and message. A live task reports `running`; a recovered or indeterminate run reports `unknown`. Do not expose the selected path. If current status cannot be retrieved, return an explicit error and do not assert an outcome.

Known, confirmed failures use allowlisted reasons for an unavailable folder, invalid or changed export, account mismatch, competing import, unavailable workbook reader, or workbook timeout. Messages offer a safe next action without exposing file paths, account references, or financial data; unknown failures retain a generic message.

### `POST /api/imports/status`

Request: `{ "id": "<opaque UUID>" }`. Return `{ "run": ..., "current": ... }` with the requested run and the latest run, independently nullable and serialized as in `/current`, from one database snapshot. Invalid IDs return 422 and unavailable storage or ownership returns 503. This allows a previously submitted request to be recovered even when a newer import exists, while still observing the current run.

### `POST /api/imports/resolve`

Request: `{ "id": "<opaque UUID>" }`. With exclusive coordinator ownership, serialize against starts and insert an `unknown` record for an absent ID, without changing an existing run. This permanently prevents a delayed start using the same ID. Return `{ "id": "<opaque UUID>" }` only after the record is durable; the response does not assert whether a previous import succeeded or failed. A running import returns 409, invalid IDs return 422, and unavailable ownership or storage returns 503. On any uncertain response, look up status again.

### `POST /api/transactions/search`

Read-only JSON request: optional `date_from`, `date_to`, `booking_status`, `text`, `category` (`{ "kind": "value", "value": "..." }` or `{ "kind": "no_recorded_category" }`), `amount_min`, `amount_max`, `cursor` and `page_size`. Dates are ISO strings; amounts are signed decimal EUR strings; omit a filter or use null to disable it. `cursor` is opaque and must be checked against the active filter set.

Response: `{ "items": [], "next_cursor": null, "history_exists": true }` (the example has no matches). Each item has `id` as an integer string, `date`, `amount_minor` as a signed integer string, `currency`, `booking_status` (`pending`, `booked`, `unknown`), `reconciliation_state`, and `ongoing_expense`. An empty page with `history_exists: false` means no history; an empty first page with `history_exists: true` means no filter matches. Apply the exact matching rules in [data-model.md](../data-model.md). Invalid filters or cursors return 422; retrieval failure returns an error, never an empty success.

### `POST /api/transactions/detail`

Request: `{ "id": "<occurrence ID>" }`. Return the list projection and `observations`, each containing `operation`, `details`, `category`, and source `booking_status`. Return 404 for a nonexistent occurrence. Include no source data for an unlinked occurrence; do not infer missing links.

### `POST /api/transactions/categories`

Return `{ "categories": ["..."] }` with distinct non-null source categories linked to existing occurrences for a filter selector; use exact stored-value matching. An explicit no-recorded-category option is always available. Values are bank suggestions; errors return an explicit failure.

## Required verification

Test loopback binding, allowed and rejected Host/Origin/token combinations, cross-origin and untrusted-text cases, no sensitive data in logs/URLs, and cache policy. Cover import success, empty, empty with unavailable storage, repeat, invalid, competing, disconnect, process restart, lock ownership loss, workbook-operation timeouts and cleanup, and commit-before-status-update ambiguity. Exercise filters (including different matching observations, no links, duplicate-looking occurrences, signed cent boundaries and invalid ranges), paging, details and empty/error distinctions against real PostgreSQL. Verify the browser journeys, including navigation blocking and refresh, with synthetic local inputs only.
