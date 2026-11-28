from typing import cast

import pytest
from sqlalchemy import Table
from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.schema import CreateTable

from personal_financial_assistant.infrastructure.models import (
    TransactionClassification,
    TransactionOccurrence,
)


@pytest.mark.parametrize(
    ("status", "state", "amount", "expected"),
    [
        ("pending", "pending-only", -1, True),
        ("pending", "pending-only", 1, False),
        ("booked", "confirmed", -1, False),
        ("pending", "unresolved", -1, False),
    ],
)
def test_ongoing_expense_requires_a_pending_debit(
    status: str, state: str, amount: int, expected: bool
) -> None:
    occurrence = TransactionOccurrence(
        booking_status=status, reconciliation_state=state, amount_minor=amount
    )
    assert occurrence.is_ongoing_expense is expected


def test_classification_mapping_checks_precision_without_rounding() -> None:
    ddl = str(
        CreateTable(cast(Table, TransactionClassification.__table__)).compile(
            dialect=dialect()
        )
    )
    assert "scale(confidence) <= 2" in ddl
    assert "NUMERIC(" not in ddl
