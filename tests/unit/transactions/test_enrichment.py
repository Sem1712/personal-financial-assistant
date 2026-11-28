import json
import logging
import traceback
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine

from personal_financial_assistant.transactions.enrichment import (
    ClassificationInput,
    EnrichmentResult,
    EnrichmentUpdate,
    update_enrichment,
)


@pytest.mark.parametrize("confidence", ["0", "0.01", "72.50", "100", "100.00", None])
def test_valid_confidence(confidence: str | None) -> None:
    update = EnrichmentUpdate.model_validate(
        {
            "category": {
                "value": "groceries",
                "status": "provisional",
                "source": "ai",
                "confidence": confidence,
            }
        }
    )
    assert update.category is not None
    assert update.category.confidence == confidence


@pytest.mark.parametrize(
    "confidence", ["-1", "100.01", "0.001", "72.500", "1e1", "01", "NaN", 1.2]
)
def test_invalid_confidence_is_rejected(confidence: object) -> None:
    with pytest.raises(ValidationError):
        EnrichmentUpdate.model_validate(
            {
                "category": {
                    "value": "groceries",
                    "status": "provisional",
                    "source": "ai",
                    "confidence": confidence,
                }
            }
        )


@pytest.mark.parametrize(
    "patch",
    [
        {},
        {
            "transaction_type": {
                "value": "groceries",
                "status": "confirmed",
                "source": "user",
            }
        },
        {
            "budget_treatment": {
                "value": "income",
                "status": "confirmed",
                "source": "user",
            }
        },
        {"category": {"value": " \t", "status": "confirmed", "source": "user"}},
        {"category": {"value": "food", "status": "unclassified", "source": "user"}},
        {"category": {"value": "food", "status": "confirmed"}},
        {"rule_explanation": "invalid"},
    ],
)
def test_invalid_patches_are_rejected(patch: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        EnrichmentUpdate.model_validate(patch)


def test_clear_is_distinct_from_omission() -> None:
    update = EnrichmentUpdate.model_validate({"category": None})
    assert update.model_fields_set == {"category"}
    assert update.category is None


@pytest.mark.parametrize("entry", ["model", "constructor", "json", "invalid_json"])
def test_validation_errors_never_expose_input(entry: str) -> None:
    secret_note = "SYNTHETIC_PRIVATE_NOTE"
    secret_category = "SYNTHETIC_PRIVATE_CATEGORY"
    data = {
        "user_annotation": secret_note,
        "category": {"value": secret_category, "status": "invalid", "source": "user"},
    }
    invalid_json = '{"user_annotation":' + json.dumps(secret_note)
    with pytest.raises(ValidationError) as raised:
        if entry == "model":
            EnrichmentUpdate.model_validate(data)
        elif entry == "constructor":
            EnrichmentUpdate(
                user_annotation=secret_note,
                transaction_type=ClassificationInput(
                    value=secret_category, status="confirmed", source="user"
                ),
            )
        elif entry == "json":
            EnrichmentUpdate.model_validate_json(json.dumps(data))
        else:
            EnrichmentUpdate.model_validate_json(invalid_json)
    error = raised.value
    rendered = "\n".join(
        [
            str(error),
            repr(error),
            str(error.errors()),
            error.json(),
            "".join(traceback.format_exception(error)),
        ]
    )
    assert secret_note not in rendered
    assert secret_category not in rendered
    assert any(reason in rendered for reason in ("status", "transaction type", "JSON"))


def test_unknown_field_name_is_not_exposed_in_validation_error() -> None:
    with pytest.raises(ValidationError) as raised:
        EnrichmentUpdate.model_validate({"SYNTHETIC_PRIVATE_NOTE": "value"})
    assert "SYNTHETIC_PRIVATE_NOTE" not in raised.value.json()
    assert "Unknown field" in str(raised.value)


def test_invalid_result_does_not_expose_notes() -> None:
    with pytest.raises(ValidationError) as raised:
        EnrichmentResult.model_validate(
            {
                "user_annotation": "SYNTHETIC_PRIVATE_NOTE",
                "category": {
                    "status": "unclassified",
                    "value": "SYNTHETIC_PRIVATE_CATEGORY",
                },
            }
        )
    assert "SYNTHETIC_PRIVATE_NOTE" not in raised.value.json()
    assert "SYNTHETIC_PRIVATE_CATEGORY" not in raised.value.json()


def test_logged_validation_failure_is_sanitized(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_note = "SYNTHETIC_PRIVATE_NOTE"
    try:
        EnrichmentUpdate.model_validate(
            {
                "user_annotation": secret_note,
                "category": {"value": " ", "status": "confirmed", "source": "user"},
            }
        )
    except ValidationError:
        logging.getLogger(__name__).exception("Invalid enrichment")
    assert secret_note not in caplog.text
    assert "Invalid category" in caplog.text


@pytest.mark.parametrize("value", ["\x1c", "\x85", "\xa0", "\u202f", "\u2003"])
def test_unicode_whitespace_only_category_is_rejected(value: str) -> None:
    with pytest.raises(ValidationError):
        EnrichmentUpdate.model_validate(
            {"category": {"value": value, "status": "confirmed", "source": "user"}}
        )


@pytest.mark.parametrize("value", ["\x00", "food\x00", "\ud800", "food\udfff"])
def test_category_with_unsupported_postgresql_text_is_rejected(value: str) -> None:
    with pytest.raises(ValidationError):
        EnrichmentUpdate.model_validate(
            {"category": {"value": value, "status": "confirmed", "source": "user"}}
        )


def test_context_with_unsupported_postgresql_text_is_rejected() -> None:
    with pytest.raises(ValidationError):
        EnrichmentUpdate.model_validate({"user_annotation": "note\x00"})


@pytest.mark.asyncio
async def test_invalid_constructed_patch_is_rejected_before_io() -> None:
    engine = MagicMock(spec=AsyncEngine)
    update = EnrichmentUpdate.model_construct(
        category=ClassificationInput.model_construct(
            value=" ", status="confirmed", source="user"
        )
    )
    with pytest.raises(ValidationError):
        await update_enrichment(engine, 1, update)
    engine.connect.assert_not_called()


def test_unclassified_result_has_explicit_empty_metadata() -> None:
    assert EnrichmentResult().category.model_dump() == {
        "value": None,
        "status": "unclassified",
        "source": None,
        "confidence": None,
    }


@pytest.mark.parametrize("value", ["expense", "income", "transfer", "refund"])
def test_each_transaction_type(value: str) -> None:
    update = EnrichmentUpdate.model_validate(
        {"transaction_type": {"value": value, "status": "confirmed", "source": "user"}}
    )
    assert update.transaction_type is not None
    assert update.transaction_type.value == value


@pytest.mark.parametrize("value", ["ordinary", "extraordinary", "excluded"])
def test_each_budget_treatment(value: str) -> None:
    update = EnrichmentUpdate.model_validate(
        {"budget_treatment": {"value": value, "status": "confirmed", "source": "rule"}}
    )
    assert update.budget_treatment is not None
    assert update.budget_treatment.value == value
