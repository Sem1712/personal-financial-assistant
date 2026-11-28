# Contract: Transaction Enrichment

## In-process write boundary

Expose typed async operations through the public `transactions` module. The update operation accepts an existing occurrence ID and a partial enrichment update and returns the resulting enrichment after a successful commit. It must not be exposed as a new browser editing endpoint.

The update body has optional `transaction_type`, `category`, `budget_treatment`, `user_annotation`, `user_explanation`, and `ai_explanation` members. Omitted member means unchanged; explicit null clears it. A supplied classification is a complete object:

```json
{
  "value": "groceries",
  "status": "provisional",
  "source": "ai",
  "confidence": "72.5"
}
```

Confidence is an optional decimal string representing a finite percentage from 0 to 100 inclusive with at most two decimal places; omitted or null means unavailable, never zero by default. Use plain decimal notation matching `(?:0|[1-9][0-9]{0,2})(?:\.[0-9]{1,2})?`, then check the range. Reject greater precision, exponent notation, leading zeros and invalid values rather than rounding. Dimension-specific allowed values, source/status rules, and context rules are defined in [data-model.md](../data-model.md). Unknown fields, an unsupported rule explanation, whitespace-only category, invalid or incomplete metadata, and invalid confidence fail the whole update without applying any change. An empty update is invalid. Not-found, validation, timeout with confirmed rollback, and other storage failures with confirmed rollback are explicit failures without raw financial data in logs. An unknown commit outcome is a distinct indeterminate result, not a confirmed failure or success; read the current state before retrying. Multi-field updates are atomic; serialization and replacement policy are defined in [data-model.md](../data-model.md).

## Existing HTTP detail response

`POST /api/transactions/detail` retains its existing `{"id": "<occurrence-id>"}` request, local security protections, error handling, existing fields and source observations. The success response adds the following `enrichment` object; all members always appear, including for legacy and newly imported occurrences:

```json
{
  "enrichment": {
    "transaction_type": {"value": "expense", "status": "confirmed", "source": "user", "confidence": null},
    "category": {"value": "groceries", "status": "provisional", "source": "ai", "confidence": "72.5"},
    "budget_treatment": {"value": null, "status": "unclassified", "source": null, "confidence": null},
    "user_annotation": null,
    "user_explanation": "Weekly food shopping",
    "ai_explanation": "The merchant resembles a grocery store"
  }
}
```

An unclassified dimension always has null value, source and confidence and status `unclassified`. Populated dimensions have complete status and source; confidence can be null. The response distinguishes user and AI explanations, and existing `observations[].category` remains the bank suggestion. Amounts, dates, currency, identifiers, observations and list/search/category contracts are unchanged. Existing not-found and sanitized storage errors remain explicit; retrieval failure must not look like unclassified data.

## Read-only interface

The existing expandable detail panel shows each dimension and its status, source and confidence, plus user annotation and separately labeled user and AI explanations. Missing items are labeled absent or unavailable; bank suggestions remain separately labeled. The UI explains that excluded is intended for future budget exclusion, not evidence that a budget has already been calculated. It presents no new edit control, list fields, filters, automatic-classification actions or model calls. All data-derived text is rendered as text rather than markup; existing keyboard, loading, failure and retry behavior is retained.
