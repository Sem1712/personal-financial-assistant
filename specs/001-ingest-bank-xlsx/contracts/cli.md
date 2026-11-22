# CLI Contract: XLSX Ingestion

## Command

```text
personal-financial-assistant ingest-xlsx --input-dir PATH
```

The command is on-demand only. It reads regular `.xlsx` files directly inside `PATH`, without recursion. Files must all refer to one selected account; the account reference is detected from the exports and is never echoed. A folder with no eligible files is a successful no-op. A folder with multiple account references fails validation without mixing them.

### Parameter Validation

CLI arguments are validated using a Pydantic `IngestXlsxParameters` model with required `input_dir: Path`. Relative paths use the current working directory. Missing/invalid parameters produce sanitized errors and a nonzero exit status; directory access checks do not run in synchronous model validators on the event loop.

### Environment Configuration

Shared settings use `pydantic-settings` to load UTF-8 `.env` from the invocation's working directory. Process environment variables override file values; parent directories are not searched.

`PFA_DATABASE_URL` is required for storage-backed ingestion and must describe an async PostgreSQL connection. Do not supply database credentials as CLI arguments. A missing `.env` is acceptable when the environment supplies required settings; missing or invalid required configuration fails explicitly.

Secrets and rejected configuration values must not appear in CLI output, model representations, or raw Pydantic validation exceptions. `.env` must remain untracked.

## Successful result

Exit status `0`. Print a summary with counts for files seen/processed/unchanged, rows read, transactions added/updated, observations unchanged, and unresolved observations. Do not include account references, transaction descriptions, dates, amounts, or raw workbook values.

An empty input folder also exits `0`, with an explicit "no eligible XLSX files" message and no database changes.

## Failure result

Nonzero exit status for invalid input, unsupported workbook structure, wrong/multiple accounts, unavailable storage, or failed atomic batch processing. Print a stable error category and a sanitized file ordinal/row location where useful. Do not print raw paths if they may expose user/account information; do not echo financial cell values.

Any file-validation or persistence failure means the entire invocation makes no transaction changes. Input workbooks are never modified.

## Reconciliation warnings

A successful import may report unresolved candidate groups. The report includes a count and sanitized reference, not financial values. Ambiguous pending observations remain pending; the command does not offer interactive matching in this version.

