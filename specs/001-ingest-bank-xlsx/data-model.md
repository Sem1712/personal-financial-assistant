# Data Model: On-Demand Bank XLSX Ingestion

This model separates transaction occurrences from source observations. The four-field matching key groups likely related observations but is not a unique transaction identifier.

## CLI Parameters and Settings (Non-Persistent)

- `IngestXlsxParameters`: Pydantic model with required `input_dir: Path`. Resolve relative paths against the invocation's working directory; validate filesystem access in offloaded I/O rather than a model validator.
- `Settings`: `pydantic-settings.BaseSettings` with required secret `database_url`, sourced from `PFA_DATABASE_URL` in `.env` or process environment. Validate an async PostgreSQL URL, keep secrets out of model/error output, and expose credentials only at the database connection boundary.
- Neither model is persisted or logged as a complete object. Configuration errors expose field names and error categories, not input values.

## Selected Account

Represents the one account selected for the current import scope.

| Field | Meaning | Validation |
|---|---|---|
| `id` | Local stable identifier | Generated locally; unique |
| `account_reference` | Bank-export account/card reference | Required; stored locally; never logged |
| `display_label` | Optional user-facing label | Optional; sanitized in CLI output |

The initial CLI accepts files for one account only. The account reference is compared after conservative whitespace normalization; it is not printed.

## Source File

Represents one unique workbook byte sequence accepted for ingestion.

| Field | Meaning | Validation |
|---|---|---|
| `sha256` | Digest of exact workbook bytes | Required; unique; calculated from the bytes parsed |
| `imported_at` | Local import timestamp | Required |
| `transaction_row_count` | Eligible transaction observations parsed | Non-negative |
| `account_id` | Selected local account | Foreign key; unknown only for an empty table with no identifiable account |

File name/path is ephemeral CLI input and is not required for identity. Store no raw workbook or original file path in the database.

## Transaction Observation

Represents the values reported by one row in one source workbook. Observations are append-only provenance; they preserve differences rather than silently overwriting one another.

| Field | Meaning | Validation |
|---|---|---|
| `source_file_sha256` | Source workbook | Required foreign key |
| `sheet_index`, `row_number` | Source location for diagnostics | Required; diagnostics avoid row content |
| `account_id` | Selected account | Required foreign key |
| `transaction_date` | Bank's transaction date | Required date; no unsupported time precision |
| `amount_minor` | Signed integer minor units | Required; exact EUR cents |
| `currency` | Currency code | Required; initially EUR only |
| `operation` | Bank operation text | Required or explicitly absent only if the export permits it |
| `details` | Bank details text | Optional; preserved as supplied |
| `booking_status` | Pending or booked | Required and normalized from supported Italian values |
| `category` | Bank's category suggestion | Optional; preserve trimmed semantic text and source observation |
| `candidate_key` | Selected account + date + amount + currency | Required; non-unique |
| `occurrence_ordinal` | 1..n count within a candidate group in this workbook | Required; preserves identical co-present rows |

Repeated observations from a byte-identical file are skipped via `Source File.sha256`. Across distinct files, reconcile group multiplicities using the maximum observed per-file count, not the sum. Preserve each accepted observation and its provenance.

## Transaction Occurrence

Represents an occurrence exposed to downstream analysis. Its candidate group is
supported by observations, but an ambiguous occurrence need not be linked to any
individual observation.

| Field | Meaning | Validation |
|---|---|---|
| `id` | Local stable identifier | Generated locally; unique |
| `account_id`, `transaction_date`, `amount_minor`, `currency` | Four-field candidate key | Required; candidate values need not be unique |
| `booking_status` | Current confirmed state | Pending, booked, or unknown (`NULL`) when unresolved |
| `observation_ids` | Individually associated source observations | Zero or more; absent when association is ambiguous |
| `reconciliation_state` | Confirmed, unresolved, or pending-only | Explicit; unresolved is not presented as booked |

Two transactions may share the same candidate key. No database unique constraint may assert that the four candidate fields identify one occurrence.

## Ingestion Run / Result

An invocation result may be represented in memory; durable run history is not required for the initial feature.

| Field | Meaning |
|---|---|
| `files_seen`, `files_processed`, `files_unchanged` | File-level counts |
| `rows_read`, `transactions_added`, `transactions_updated` | Row and occurrence counts |
| `observations_unchanged`, `unresolved_observations` | Idempotency and reconciliation results |
| `errors` | Sanitized file/row references and error codes; no raw financial values |

## State and Validation Rules

- Parse and validate the full input batch before changing persistent transaction state.
- Persist accepted imports and observations in one PostgreSQL transaction; any invalid eligible file or persistence failure rolls back the batch.
- A candidate group contains all observations with equal selected account, date, exact signed cents, and currency. Status, operation, details, and category are not key fields.
- For each workbook, count identical candidate-key occurrences. Across workbook snapshots, stored multiplicity is the maximum observed count, not the sum.
- Match a single pending occurrence to a single booked observation in the same candidate group only when that association is unambiguous. When multiple candidates compete, retain pending state and report the booked observation as unresolved.
- When multiplicity grows but the additional occurrence cannot be associated with an
  individual observation, its booking status is unknown, not invented; the original
  observation statuses remain available and no arbitrary link is made.
- Never infer cancellation from omission from a later export; never auto-link observations whose candidate key changed.
- A booked state never regresses to pending. Preserve conflicting source values in observations and report when no representative value is unambiguous.
- The max-multiplicity rule can undercount genuinely distinct, identical-key transactions split across exports. This limitation is inherent in the source data and must not be hidden.

## Schema migration

The initial ingestion revision has no earlier ingestion schema. Revision
`0002_unknown_status` upgrades that supported schema, preserving source observations
while clearing invented statuses and arbitrary links from previously unresolved
occurrences. Downgrading is refused while any occurrence has an unknown status.
Revision `0003_empty_source` allows accountless empty files so their digests can be
tracked without inventing account details; downgrade is refused while such files exist.
When an empty file contains an identifiable `Conti e Carte:` account header, it is
validated and recorded; re-import also fills previously unknown source-account metadata.
