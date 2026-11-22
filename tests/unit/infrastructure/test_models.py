import pytest

from personal_financial_assistant.infrastructure.models import TransactionOccurrence


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
