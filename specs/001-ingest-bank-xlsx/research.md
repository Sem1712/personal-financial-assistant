# Research: On-Demand Bank XLSX Ingestion

**Date**: 2026-11-22

## XLSX Reader

**Decision**: Use `python-calamine` (research version 0.9.1), pending a dependency-resolution and smoke test on the repository's Python 3.15 interpreter.

**Rationale**:

- PyPI metadata fetched 2026-11-22 lists Python 3.15 support and a CPython 3.15 wheel. This is a closer match to the repository's `requires-python >=3.15` than the alternative checked.
- Calamine provides workbook/sheet access and row iteration without the DataFrame conversion and implicit type/coercion layer of pandas.
- Its reader loads sheet data into memory, so retain compressed and expanded workbook safety limits. No performance benchmark is required.
- The reader is synchronous; use sequential, awaited offloading so file I/O does not block the asyncio event loop. No concurrent parsing pipeline is necessary.

**Alternatives considered**:

- `openpyxl` has read-only/lazy worksheet modes and is suitable when detailed cell formatting is required. PyPI metadata fetched 2026-11-22 did not establish Python 3.15 classifier support, and its latest release observed by the research was 3.1.5 (2024-06-28). Python 3.15 compatibility is plausible but unverified. Its documentation also calls out explicit workbook closing in optimized mode.
- `pandas` is unnecessary for this row-oriented import, adds a larger dependency surface, and may introduce float/type inference that is inappropriate for exact financial parsing.

**Parsing rules**:

- Normalize heading whitespace and case; find exactly one row containing the eight required headings. Do not assume a row offset because the workbook has a variable preamble.
- Accept only the documented single-account layout; fail if headings are absent/duplicated or transaction rows fail required-field validation.
- Prefer date/date-time values supplied by the XLSX reader. If a date-formatted cell is returned as a serial, convert only after determining the workbook's date system; reject unsupported or ambiguous serials and non-midnight times.
- Convert numeric amounts through their shortest decimal string to `Decimal`, then to integer cents after verifying no nonzero sub-cent precision. Never construct `Decimal` directly from a binary float.
- No formulas are evaluated. The implementation must reject formula-based required transaction cells or otherwise demonstrate that the library returns a trustworthy cached value; this needs a focused library smoke test before finalizing parser behavior.

## Idempotent Import Without Bank Transaction IDs

**Decision**: Treat the user's key—selected account, transaction date, exact signed amount, and currency—as a candidate group only. Store source observations and their file provenance. Use file SHA-256 to make byte-identical repeated/renamed workbooks no-ops; for distinct workbook snapshots, preserve the maximum observed count of each candidate group, not the sum of counts. Do not impose a uniqueness constraint on the four key fields.

**Rationale**:

- Summing group counts across overlapping exports multiplies transactions that appear in more than one file.
- Keeping only one row per key loses same-day repeated purchases with identical values.
- A full-row fingerprint changes when status or descriptive fields change and therefore cannot be the bank transaction's identity.
- A per-file multiset preserves the number of identical occurrences co-present in an export. Comparing snapshot multiplicity by maximum makes repeated and overlapping imports idempotent and deterministic.
- Pending-to-booked matching is limited to the same candidate group and only when a one-to-one association is unambiguous. If multiple occurrences compete, keep existing pending occurrences pending, retain the booked observation as unresolved, and report it. Do not match when account/date/amount/currency differs.

**Hard limitation**: No algorithm can infer whether one same-key row seen in each of two files is one repeated observation or two real transactions if the exports never show both occurrences together. Maximum multiplicity may undercount in that case. State this plainly in user documentation and the CLI's ambiguity report; do not claim exact real-world uniqueness.

**Alternatives considered**:

- Sum rows across files: rejected because overlapping exports create duplicates.
- Deduplicate all rows by four-key value: rejected because it collapses legitimate identical transactions.
- Hash all row columns: rejected as the identity key because pending-to-booked or description/category changes alter the hash.
- Replace all transactions in the latest export: rejected because exports may be partial/filtered and absence is not evidence of cancellation.

## Handling Local XLSX Files

**Decision**: Treat workbooks as untrusted input even though the expected source is a local bank download.

- Set explicit limits on compressed file size, total uncompressed ZIP size, compression ratio, and ZIP entry count before parsing. Initial values proposed for prototype: 20 MiB compressed, 200 MiB uncompressed, 100:1 maximum ratio, and 500 entries. Revisit only if legitimate sample files exceed these bounds.
- Accept `.xlsx` only; reject macro-bearing workbooks, external-link package parts, password-protected/corrupt workbooks, and required formula cells. Do not evaluate formulas or fetch linked content.
- Exclude temporary lock files beginning `~$`; do not follow symlinks or recursively search directories.
- Read each file once into bounded memory, compute its digest from the same bytes parsed, and perform no filesystem writes to the source directory.
- Emit only counts and a redacted file/row reference on errors. Never print account values, transaction fields, amounts, or raw workbook content.

Thresholds are conservative workbook safety limits, not performance targets, standards, or bank requirements. Verify legitimate workbook compatibility and boundary rejection with synthetic fixtures; no benchmark workload is required.

## CLI Parameters and Environment Settings

**Decision**: Use Pydantic `BaseModel` for CLI parameters and `pydantic-settings.BaseSettings` for `.env` and process-environment settings, as requested by the user.

**Rationale**: Keep typed parameter validation and configuration loading explicit without introducing a custom environment parser. Use a required input-directory `Path` in the CLI model and a required secret database URL in shared settings. Validate types and URL scheme without performing I/O in model validators.

**Loading policy**: Read UTF-8 `.env` in the invocation's working directory, without parent-directory discovery. Use the `PFA_` environment prefix; process environment overrides `.env`. Missing required settings fail with field names and error categories only, never rejected values or raw validation exception output.

**Async policy**: The user declined an exception to the constitution's async-first rule. Settings construction that reads `.env` and filesystem/XLSX operations remain offloaded; database access remains async. Sequential orchestration is preferred over unnecessary concurrency.

**Alternatives considered**: Manual dotenv parsing and custom CLI validation are rejected in favor of the user's Pydantic request. Changing to synchronous database access or permitting blocking I/O on the event loop is not approved.

## References

- [python-calamine on PyPI](https://pypi.org/project/python-calamine/) and [PyPI JSON metadata](https://pypi.org/pypi/python-calamine/json), fetched 2026-11-22.
- [python-calamine repository](https://github.com/dimastbk/python-calamine), README and type stubs inspected 2026-11-22.
- [openpyxl optimized modes](https://openpyxl.readthedocs.io/en/stable/optimized.html), fetched 2026-11-22.
- [openpyxl on PyPI](https://pypi.org/project/openpyxl/), package metadata inspected 2026-11-22.

