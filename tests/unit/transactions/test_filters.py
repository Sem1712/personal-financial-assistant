from datetime import date

import pytest
from pydantic import ValidationError

from personal_financial_assistant.transactions.filters import TransactionFilters


@pytest.mark.parametrize(
    ("value", "cents"),
    [
        ("0", 0),
        ("-12.34", -1234),
        ("+0.01", 1),
        (".5", 50),
        ("92233720368547758.07", 2**63 - 1),
        ("-92233720368547758.08", -(2**63)),
    ],
)
def test_exact_euro_amounts(value: str, cents: int) -> None:
    filters = TransactionFilters.model_validate({"amount_min": value})
    assert filters.amount_min == cents


@pytest.mark.parametrize(
    "value",
    [
        "1.001",
        "92233720368547758.08",
        "-92233720368547758.09",
        "NaN",
        "1e2",
        "",
        "1,23",
    ],
)
def test_invalid_amounts_are_rejected(value: str) -> None:
    with pytest.raises(ValidationError):
        TransactionFilters.model_validate({"amount_min": value})


@pytest.mark.parametrize(
    "values",
    [
        {"date_from": "2025-02-01", "date_to": "2025-01-31"},
        {"amount_min": "2", "amount_max": "1"},
        {"booking_status": "other"},
        {"text": "invalid\0text"},
        {"category": {"kind": "value", "value": "invalid\0category"}},
        {"category": {"kind": "value", "value": ""}},
        {"page_size": 0},
        {"page_size": 101},
        {"page_size": True},
        {"date_from": 1234},
        {"unrecognized": "value"},
    ],
)
def test_invalid_filters_are_rejected(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        TransactionFilters.model_validate(values)


def test_cursor_is_bound_to_filters_and_validated() -> None:
    first = TransactionFilters.model_validate({"text": "shop", "amount_min": "-1"})
    cursor = first.encode_cursor(date(2025, 1, 2), 42)
    resumed = TransactionFilters.model_validate(
        {"text": "shop", "amount_min": "-1.00", "cursor": cursor}
    )
    assert resumed.cursor_position() == (date(2025, 1, 2), 42)
    with pytest.raises(ValidationError):
        TransactionFilters.model_validate({"text": "other", "cursor": cursor})
    for invalid in ("not-a-cursor", cursor + "!", "e30"):
        with pytest.raises(ValidationError):
            TransactionFilters.model_validate({"cursor": invalid})
