# Research: Financial Assistant Interface

## Local UI technology

**Decision**: Add a loopback-only FastAPI/Uvicorn service with locally served HTML, CSS and browser-native JavaScript. Extend the existing `personal-financial-assistant` CLI with `serve-ui`; retain the existing command unchanged. Keep all assets local.

**Rationale**: Async request handling and typed contracts fit the existing asyncio and Pydantic application. A small same-origin frontend avoids a second package manager, a frontend build pipeline and third-party data requests. Exact dependency versions and Python 3.15 compatibility must be verified and locked with uv during implementation.

**Alternatives considered**: A separate frontend project adds tooling without a current need; a desktop shell adds platform packaging and a UI dependency. A blocking standard-library server would conflict with async-first runtime I/O.

## Loopback security and sensitive data

**Decision**: Bind only to `127.0.0.1` with a fixed documented port. Validate the exact expected Host and port, reject foreign Origin on requests, use a startup-generated unpredictable token in a custom header for every data request, reject unsafe cross-origin or missing-origin requests, accept only JSON for state-changing requests, and do not enable CORS. Serve no external scripts, fonts or images; escape or use text-only DOM insertion for every source value. Set a restrictive Content Security Policy, frame protection, and `Cache-Control: no-store`; suppress request body, query and access logging that could disclose financial values or paths. Tokens and response data must never be embedded in URLs or logged.

**Rationale**: Loopback binding alone does not establish that a browser request came from this UI. Exact Host checks reduce exposure to attacker-controlled hostnames resolving to loopback, while the origin, token and content-type checks address cross-site requests; safe rendering reduces XSS risk. CORS is not a CSRF defense. These controls do not protect against a malicious local process running as the same user; that is outside the single-user trust model.

**Alternatives considered**: Wildcard hosts or CORS permit unnecessary exposure. A token alone does not address untrusted displayed text. User accounts or a remotely reachable deployment exceed the specified local scope.

**References**: [FastAPI trusted host middleware](https://fastapi.tiangolo.com/advanced/middleware/), [OWASP CSRF prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html), [MDN CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS), [MDN Fetch Metadata](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Sec-Fetch-Site). The Host-based rebinding mitigation is a design inference, not a claim that the FastAPI page fully specifies DNS-rebinding defense.

## Import lifetime and recovery

**Decision**: An owned asyncio task runs each accepted import; only one can run through the UI at a time. Store an import-run row in PostgreSQL before scheduling work, with no folder path or financial details. Keep its final sanitized result, or mark its outcome unknown if completion cannot be confirmed. On startup or recovery, acquire a dedicated session-level PostgreSQL advisory lock before declaring old running UI jobs unknown. Only one UI process may hold that lock; release it on shutdown and fail closed if ownership is lost.

**Rationale**: Closing a browser must not erase the evidence that an import was started. A durable run row makes reconnection and restart recovery possible without storing sensitive input paths. An import can commit before the final result is recorded, so an interrupted run cannot safely be classified as success or failure. A separate singleton lock avoids mistaking a live job in another UI process for a stale one; the ingestion service's existing transaction-level advisory lock still protects concurrent CLI writes.

**Alternatives considered**: Browser or process memory alone loses state on closure/restart. Automatically retrying an unknown import hides uncertainty. Treating every interrupted run as failed is incorrect if the transaction already committed. A generic task queue or persistent job history is unnecessary.

**Reference**: [FastAPI background tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/) describes background responses but does not itself provide durable job recovery.

## Workbook timeouts and storage availability

**Decision**: For UI imports, use one local worker subprocess for workbook discovery, individual reads and final snapshot verification, with 60-second per-operation deadlines and the bounded termination/reaping policy in [data-model.md](./data-model.md#workbook-deadlines-and-cleanup). Require PostgreSQL before a UI import starts, including for an empty folder; preserve the existing CLI's database-independent empty-folder behavior.

**Rationale**: The existing offloaded workbook calls have no timeout, and cancelling an await on a thread does not terminate the underlying operation. A worker without database access lets the UI enforce deadlines without allowing timed-out work to commit. Requiring storage first makes every accepted UI run recoverable.

**Alternatives considered**: Timing out only the thread await leaves a potentially stuck worker running. Checking for an empty folder before recording a run breaks the UI's durable recovery contract when storage is unavailable. Reusing the CLI entry point in a subprocess would not bind ingestion writes to the UI's pinned lock connection.

## Transaction reading and exact filters

**Decision**: Add a read-only transaction service over existing occurrences and their explicitly linked observations. Use correlated existence checks for text and category filters so observations do not multiply occurrences. Category and text may match different linked observations. “No recorded category” matches when no linked observation has a non-null category, including when there are no linked observations; label this as absence of recorded evidence, not a definitive classification. Use inclusive signed integer EUR-cent boundaries; parse decimal text exactly and reject sub-cent values. Provide stable date/id ordering and bounded pagination.

**Rationale**: Occurrences, not source rows, are the displayed entities. Some unresolved occurrences have no linked observation, and competing source observations may disagree. Integer cents and decimal strings avoid precision loss, including in browser JSON.

**Alternatives considered**: Joining raw observations into the main list can duplicate occurrences. Choosing one source category would erase disagreement; floating-point money filters can produce incorrect boundaries. Loading all rows into the browser is unbounded.

## Folder input and accessibility

**Decision**: Provide a clearly labeled local folder-path field with validation; this satisfies the user's folder-only choice without assuming browsers can expose a usable native folder path. Use semantic controls, visible labels, keyboard navigation and announced status/error changes.

**Rationale**: Browser file pickers do not reliably return an absolute host directory to a web service. A local path input preserves the existing importer without uploading or copying exports. No specific accessibility certification or performance SLA was requested.

**Alternatives considered**: File uploads change folder semantics and require copying financial files; an OS-native folder dialog requires an additional desktop integration not justified for the first release.
