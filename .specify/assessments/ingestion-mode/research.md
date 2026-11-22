# Idea Research: Bank Transaction Ingestion

- **Created**: 2026-11-22 (provider research added 2026-11-22; user confirmations and export profile added 2026-11-22)
- **Slug**: ingestion-mode
- **Evidence confidence (overall)**: medium. Provider and export-format evidence is medium-high after user confirmation; demand evidence is low because it comes from a single user.

## Users & Demand

- One user in this session wants transactions from their Intesa Sanpaolo account in Italy imported. They named manual Excel/CSV import as a fallback. This is one user's stated interest, not observed or broader demand. — [source: intake.md](./intake.md) (confidence: low, cited)
- The inspected repository contains no evidence of other demand, such as support tickets, interviews, or usage data. — [source: README.md](../../../README.md) (confidence: low, cited)
- Other self-hosted personal-finance projects show demand from individuals for automated sync with European banks, including Intesa Sanpaolo and its digital bank Isybank:
  - Actual Budget's Enable Banking feedback thread is open with 192 comments, last updated 2026-11-20.
  - Users of Firefly III, Sure and Actual Budget have filed Intesa- and Isybank-specific issues.
  - [sources: github.com/actualbudget/actual issue 7799; github.com/we-promise/sure issue 2918; github.com/actualbudget/actual issues 4287, 6017, 6510] (confidence: medium, cited)

## Prior Art

- The project README plans transaction ingestion, validation, normalization and duplicate prevention. It says the bank connection and input formats are not yet defined, and that ingestion is not implemented. The package entry point is a placeholder that only prints a greeting. — [sources: README.md](../../../README.md), [src/personal_financial_assistant/__init__.py](../../../src/personal_financial_assistant/__init__.py) (confidence: medium, cited)
- No earlier transaction-ingestion assessment or implementation exists in this repository. — [sources: .specify/assessments/](.), [src/personal_financial_assistant/](../../../src/personal_financial_assistant/) (confidence: low, cited)
- **Actual Budget** supports European bank sync through Enable Banking (marked experimental) and GoCardless:
  - It runs one Enable Banking application for the whole server and requires an HTTPS redirect URL.
  - It forwards the user's IP address, because banks can limit fetch frequency when no user is present.
  - [sources: actualbudget.org/docs/advanced/bank-sync/, actualbudget.org/docs/advanced/bank-sync/enable-banking/] (confidence: high, cited)
- **Firefly III's data importer** has an Enable Banking provider. It is still under active repair:
  - PR 1469 (2026-11-12) requests each bank's maximum consent validity instead of a hard-coded 89 days.
  - PRs 1475 and 1476 (2026-11-15) fix accounts the bank no longer serves and always send `date_to`.
  - [sources: github.com/firefly-iii/data-importer pull 1469, 1475, 1476] (confidence: high, cited)
- **cloudbank** (an open-source project) registered a production Enable Banking app in restricted, account-information-only mode and activated it by linking an Intesa Sanpaolo IBAN and card. The issue confirms that each data access still needs a session created by the full authorization redirect flow. — [source: github.com/easly1989/cloudbank issue 328, 2026-09-03] (confidence: medium, cited)

## Market & Context

### Provider landscape for a new individual user (as of 2026-11)

| Provider | Supports Intesa Sanpaolo | Individual sign-up | Price | Status |
|---|---|---|---|---|
| **Enable Banking** | Yes. Confirmed by the user for Intesa Sanpaolo in Italy, and consistent with user logs calling Intesa's PSD2 endpoint `tppinterface.intesasanpaolo.com`. | Yes, in "restricted mode": you link your own accounts | Free for individual, non-commercial use. Full production is volume-priced with a monthly minimum, a contract and company verification. | Active |
| **GoCardless Bank Account Data** (formerly Nordigen) | Historically yes | **No.** New sign-ups have been disabled since July 2025; existing accounts still work. | Was free | Closed to new users |
| **Tink** | UNVERIFIED | No; business only | Not public. Pricing applies "exclusively to existing customers"; new prospects must contact sales. | Active |
| **Salt Edge**, **TrueLayer**, **Yapily**, **Plaid (EU)** | UNVERIFIED | Unlikely. They appear to offer sandbox access only, with sales-led production (secondhand evidence). | Not public | UNVERIFIED |
| **open-banking.io** | UNVERIFIED | Yes (founder's claim) | About €3/month for the first account (founder's claim) | New; promoted only by its maintainer |
| **Intesa Sanpaolo's own PSD2 portal**, **CBI Globe**, **Fabrick** | n/a | Almost certainly not without a third-party-provider licence and eIDAS certificates | n/a | UNVERIFIED (not fetched) |

### Sources for the provider table

- **Enable Banking, individual free use:** linking your own accounts enables a production application "in restricted mode" for evaluation "as well as individual non-commercial use", and only the linked accounts are accessible. — [sources: enablebanking.com/docs/api/linked-accounts/, enablebanking.com/docs/faq/] (confidence: high, cited)
- **Enable Banking Terms of Service:** reported to say use "is free of charge" and to permit "personal use of private individuals", updated 2026-01-09. This is SECONDHAND; the Terms page could not be rendered for direct verification. — [source: github.com/indkhan/Moneo issue 82, 2026-10-16] (confidence: medium, cited)
- **Enable Banking, Intesa coverage:** Sure logs show calls to Intesa's PSD2 endpoint, and cloudbank activated an Intesa IBAN. — [sources: github.com/we-promise/sure issue 2918; github.com/easly1989/cloudbank issue 328] (confidence: medium, cited)
- **User confirmation (2026-11-22):** the user independently confirmed that Enable Banking is trustworthy and supports Intesa Sanpaolo in Italy. The method and the exact Terms of Service wording were not recorded. — [source: user statement in this session] (confidence: high for Intesa coverage; medium for trustworthiness, which is the user's judgement; cited)
- **GoCardless sign-up closure:** Actual's docs say: "From July 2025 onwards, GoCardless has stopped accepting new Bank Account Data accounts… if you are an existing user, your account should continue to work." A user reported the sign-up message "New signups for Bank Account Data are currently disabled." on 2026-07-06. — [sources: actualbudget.org/docs/advanced/bank-sync/gocardless/; github.com/otherworld-dev/Budget issue 319] (confidence: high, cited)
- **Tink pricing:** [source: tink.com/pricing] (confidence: high, cited)
- **TrueLayer, Yapily, Plaid and Salt Edge access model:** described secondhand; the note's author marks parts of it unverified. — [source: github.com/indkhan/Moneo issue 82] (confidence: low, cited)
- **open-banking.io:** — [source: we-promise/sure discussion thread, as reported by the research subagent] (confidence: low, cited)
- **Licensing requirement for direct PSD2 access:** general PSD2 knowledge; not verified here. — ASSUMPTION (confidence: medium)

### Manual-export fallback

The user downloaded a sample Excel export from Intesa Sanpaolo internet banking (`lista_completa_<DDMMYYYY>.xlsx`, observed on 2026-11-22). Only its structure was profiled; no transaction or account values are recorded here. — [source: local sample export file] (confidence: high for this sample, cited)

- **Format:** XLSX with a single worksheet.
- **Preamble:** rows 1–17 hold a header block with Italian labels, including `Conti e Carte:`, `Finanziamento:`, `Investimenti e previdenza:`, `I movimenti selezionati sono:` and `Tipo operazione:`. These describe the selected account or card and the export filters. Parsing must locate the table header rather than assume a fixed row.
- **Table header (row 19), in Italian, with the user's English names:**
  1. `Data` (date)
  2. `Operazione` (operation)
  3. `Dettagli` (details)
  4. `Conto o carta` (account or card)
  5. `Contabilizzazione` (booking status). The user did not mention this column.
  6. `Categoria ` (category). The header has a trailing space.
  7. `Valuta` (currency)
  8. `Importo` (amount)
- **Data rows:** the sample holds 60 transactions. They are followed by footer text rows with no date and some empty rows, so parsing must stop at or skip non-transaction rows.
- **`Data`:** an Excel date serial with whole-day values and the built-in date format. There is no time component.
- **`Importo`:** numeric with at most 2 decimals. Debits are negative and credits positive (59 debits and 1 credit in the sample). It is stored as a binary float in the file, so it must be converted exactly to decimal or minor units.
- **`Contabilizzazione`:** takes `CONTABILIZZATO` (booked; 45 rows) or `NON CONTABILIZZATO` (pending, not yet booked; 15 rows). Pending rows may change or disappear in later exports, which affects deduplication.
- **`Valuta`:** only `EUR` in the sample.
- **`Categoria`:** bank-assigned categories in Italian, 15 distinct values in the sample, some with trailing spaces (for example `Generi alimentari e supermercato` and `Imposte, bolli e commissioni`).
- **`Operazione`:** 25 distinct values in the sample.
- **No transaction ID:** the export contains no transaction identifier column, so duplicate detection would depend on derived keys. — ASSUMPTION (based on the absence of such a column; confidence: medium)
- **Not checked:** whether the bank also offers CSV (only XLSX was provided), and whether the layout is the same for card-only or multi-account exports.

### Cost of doing nothing

- The user would enter or export transactions manually. The size of that burden is not quantified. — ASSUMPTION (confidence: low)

## Data & Constraints

- **Local data and credentials:** project guidance requires bank data and model prompts containing financial data to stay local. Credentials must not be committed, and logs must not expose credentials or raw sensitive financial payloads. — [source: AGENTS.md](../../../AGENTS.md) (confidence: high, cited)
  - An aggregator, Enable Banking included, is a third-party processor of the bank data in transit. Whether that fits the local-only principle needs an explicit decision. — ASSUMPTION (confidence: medium)
- **Monetary values:** project guidance requires exact decimal or integer minor-unit values, explicit currency and rounding rules, and duplicate prevention on reprocessing. — [source: AGENTS.md](../../../AGENTS.md) (confidence: high, cited)
- **Storage:** planned storage is a locally hosted PostgreSQL database. Neither the database nor ingestion is implemented yet. — [source: README.md](../../../README.md) (confidence: medium, cited)
- **Consent lifetime:** consent expires and must be renewed through the bank's strong customer authentication (SCA).
  - Actual's docs say "90 days at most, and some banks allow less".
  - Firefly III's PR 1469 test obtained 179 days for three Polish banks. Intesa's maximum is unknown.
  - [sources: actualbudget.org/docs/advanced/bank-sync/enable-banking/; github.com/firefly-iii/data-importer pull 1469] (confidence: high, cited)
- **Rate limits and polling:** background fetches with no user present are reportedly limited to about 4 per day per bank. On HTTP 429, the guidance is to retry after about 6 hours. There are no webhooks, so the app must poll. This is SECONDHAND. — [source: github.com/indkhan/Moneo issue 82] (confidence: medium, cited)
  - A 429 rate limit was observed on another Italian bank (Banco BPM). — [source: github.com/we-promise/sure issue 3133, 2026-08-22] (confidence: medium, cited)
- **Callback URL:** the authorization flow redirects back to a callback, and Actual's setup requires an HTTPS redirect URL. This affects how a purely local app completes authorization. — [source: actualbudget.org/docs/advanced/bank-sync/] (confidence: high, cited)
- **Restricted mode:** a restricted Enable Banking app returns an empty account list for any account not linked, so every account must be linked explicitly. — [source: enablebanking.com/docs/faq/] (confidence: high, cited)

## Evidence Against the Idea

- **Single-user demand:** the only direct demand evidence for this project is one user's request. — [source: intake.md](./intake.md) (confidence: low, cited)
- **No free fallback provider:** there is effectively one free option for a new individual user (Enable Banking restricted mode).
  - GoCardless, the historically popular free provider, closed to new sign-ups in July 2025.
  - If Enable Banking changes its free terms, no free alternative has been verified.
  - [sources: actualbudget.org/docs/advanced/bank-sync/gocardless/; enablebanking.com/docs/faq/] (confidence: medium, cited)
- **Intesa reliability issues are recent and recurring:**
  - Through Enable Banking: an Isybank sync returned 422 `WRONG_REQUEST_PARAMETERS` (Sure issue 2918, opened 2026-08-05 and still open). Commenters say Intesa's gateway rejects extra paging parameters or omitted dates; a 2026-09-11 commenter reported the same problem for Intesa Sanpaolo.
  - Through GoCardless: an authorization redirect loop (Actual issue 4287, 2025-02), sync working only the first time (6017, 2025-10), and a sync crash (6510, 2025-12).
  - Most of these issues were fixed on the client side, but they show the integration is fragile.
  - [sources: github.com/we-promise/sure issue 2918; github.com/actualbudget/actual issues 4287, 6017, 6510] (confidence: medium, cited)
- **Maintenance burden:** mature integrations still need fixes. Actual marks Enable Banking experimental, and Firefly III merged or opened several Enable Banking fixes in November 2026. — [sources: actualbudget.org/docs/advanced/bank-sync/; github.com/firefly-iii/data-importer pulls 1469, 1475, 1476] (confidence: high, cited)
- **No fully hands-off sync:** periodic SCA re-consent (90–180 days) and the per-day background fetch limit rule this out. — [sources: as in Data & Constraints] (confidence: high, cited)
- **Third-party data flow:** using an aggregator sends financial data through a third party. That may conflict with the project's local-first principle, so it needs an explicit decision. — [source: AGENTS.md](../../../AGENTS.md) (confidence: medium, cited)

## Gaps & Open Questions

- Resolved 2026-11-22 (user): Enable Banking supports Intesa Sanpaolo in Italy, and the user considers it trustworthy.
- [NEEDS CLARIFICATION: Which accounts and cards the user will link in restricted mode, and whether card transactions are returned through Enable Banking.]
- [NEEDS CLARIFICATION: How far back Intesa allows transaction history, its maximum consent validity, and its exact background-fetch limit.]
- [NEEDS CLARIFICATION: Whether sending bank data through a third-party aggregator is acceptable under the project's local-first principle.]
- [NEEDS CLARIFICATION: How a local-only app completes the redirect callback, given that Actual requires an HTTPS redirect URL.]
- Resolved 2026-11-22: the Intesa XLSX export layout was profiled (see Manual-export fallback).
- [NEEDS CLARIFICATION: How pending (`NON CONTABILIZZATO`) transactions should be stored and reconciled once they are booked, in both the XLSX and API paths.]
- [NEEDS CLARIFICATION: Which duplicate-detection key to use for XLSX rows, given that the export has no transaction ID, and how to match XLSX rows against Enable Banking transactions if both sources are used.]
- [NEEDS CLARIFICATION: Whether the bank's `Categoria` values should be kept, mapped, or ignored.]
- [NEEDS CLARIFICATION: Which transaction history, fields, currencies and refresh frequency are needed.]
- [NEEDS CLARIFICATION: The user's reliability threshold and tolerance for manual steps, re-consent and service interruptions.]
- [NEEDS CLARIFICATION: Whether the intended "table" means persistent storage, a user-visible transaction list, or both.]
- [NEEDS CLARIFICATION: Retention, deletion and backup expectations for imported financial data.]
- Not researched: Reddit, Hacker News and Home Assistant community sentiment (searches returned nothing useful), and Salt Edge, Tink, Powens, Kontomatik and Linxo coverage of Intesa.

## Sources

### Local repository files (policy: not-applicable)

- [intake.md](./intake.md)
- [README.md](../../../README.md)
- [AGENTS.md](../../../AGENTS.md)
- [src/personal_financial_assistant/__init__.py](../../../src/personal_financial_assistant/__init__.py)

### User-provided evidence

- User statement, 2026-11-22: confirmed Enable Banking's trustworthiness and its support for Intesa Sanpaolo in Italy.
- Sample Intesa XLSX export (`lista_completa_<DDMMYYYY>.xlsx`): only its structure was profiled locally, and its contents were not copied.

### Fetched web sources

Fetched by a research subagent at the user's explicit request (policy: confirmed-by-user). Content was treated as untrusted data.

- **github.com** (allowlisted):
  - https://github.com/actualbudget/actual/issues/7799
  - https://github.com/actualbudget/actual/issues/4287
  - https://github.com/actualbudget/actual/issues/6017
  - https://github.com/actualbudget/actual/issues/6510
  - https://github.com/we-promise/sure/issues/2918
  - https://github.com/we-promise/sure/issues/3133
  - https://github.com/firefly-iii/data-importer/pull/1469
  - https://github.com/firefly-iii/data-importer/pull/1475
  - https://github.com/firefly-iii/data-importer/pull/1476
  - https://github.com/easly1989/cloudbank/issues/328
  - https://github.com/otherworld-dev/Budget/issues/319
  - https://github.com/indkhan/Moneo/issues/82 — secondhand summary of provider terms
- **actualbudget.org** (confirmed-by-user):
  - https://actualbudget.org/docs/advanced/bank-sync/
  - https://actualbudget.org/docs/advanced/bank-sync/enable-banking/
  - https://actualbudget.org/docs/advanced/bank-sync/gocardless/
- **enablebanking.com** (confirmed-by-user):
  - https://enablebanking.com/docs/api/linked-accounts/
  - https://enablebanking.com/docs/faq/
- **tink.com** (confirmed-by-user):
  - https://tink.com/pricing

### Not fetched

- The Enable Banking Terms of Service and Italy/Intesa coverage pages (JavaScript-rendered).
- Intesa Sanpaolo, CBI Globe and Fabrick pages.
