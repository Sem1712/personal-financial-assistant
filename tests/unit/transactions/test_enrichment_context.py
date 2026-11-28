import pytest
from pydantic import ValidationError

from personal_financial_assistant.transactions import EnrichmentUpdate


def test_context_fields_are_independent_and_preserve_text() -> None:
    patch = EnrichmentUpdate.model_validate(
        {
            "user_annotation": "  note  ",
            "user_explanation": "user",
            "ai_explanation": "AI",
        }
    )
    assert patch.model_dump(exclude_unset=True) == {
        "user_annotation": "  note  ",
        "user_explanation": "user",
        "ai_explanation": "AI",
    }
    cleared = EnrichmentUpdate.model_validate({"user_explanation": None})
    assert cleared.model_dump(exclude_unset=True) == {"user_explanation": None}


@pytest.mark.parametrize(
    "patch",
    [
        {"user_annotation": 3},
        {"rule_explanation": "not supported"},
        {
            "user_annotation": "valid",
            "category": {"value": " ", "status": "confirmed", "source": "user"},
        },
    ],
)
def test_invalid_context_patch_is_rejected(patch: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        EnrichmentUpdate.model_validate(patch)
