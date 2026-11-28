import pytest
from pydantic import ValidationError

from personal_financial_assistant.transactions import (
    ClassificationInput,
    ClassificationResult,
)


@pytest.mark.parametrize("source", ["ai", "rule", "user"])
@pytest.mark.parametrize("status", ["provisional", "confirmed"])
def test_supported_provenance(source: str, status: str) -> None:
    value = ClassificationInput.model_validate(
        {"value": "food", "status": status, "source": source}
    )
    assert value.source == source
    assert value.status == status
    assert value.confidence is None


@pytest.mark.parametrize(
    "value",
    [
        {"value": "food", "status": "confirmed", "source": "other"},
        {"value": "food", "status": "unclassified", "source": "ai"},
        {"value": "food", "status": "confirmed", "source": None},
    ],
)
def test_invalid_provenance(value: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ClassificationInput.model_validate(value)


def test_unclassified_result_cannot_retain_provenance() -> None:
    with pytest.raises(ValidationError):
        ClassificationResult.model_validate({"status": "unclassified", "source": "ai"})
