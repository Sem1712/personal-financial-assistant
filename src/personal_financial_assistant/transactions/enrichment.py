"""Typed, occurrence-scoped enrichment, independent of imported observations."""

import asyncio
import re
from decimal import Decimal
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    GetCoreSchemaHandler,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic.config import ExtraValues
from pydantic_core import InitErrorDetails, PydanticCustomError, core_schema
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from personal_financial_assistant.infrastructure.models import (
    TransactionClassification,
    TransactionContext,
    TransactionOccurrence,
)

Dimension = Literal["transaction_type", "category", "budget_treatment"]
Source = Literal["ai", "rule", "user"]
Status = Literal["provisional", "confirmed"]
DIMENSIONS: tuple[Dimension, ...] = ("transaction_type", "category", "budget_treatment")
CONTEXT_FIELDS = ("user_annotation", "user_explanation", "ai_explanation")

_SAFE_FIELDS = frozenset(
    (*DIMENSIONS, *CONTEXT_FIELDS, "value", "status", "source", "confidence")
)
_SAFE_REASONS = frozenset(
    {
        "An enrichment update must not be empty",
        "Invalid transaction type",
        "Invalid budget treatment",
        "Invalid category",
        "Invalid confidence percentage",
        "Text contains unsupported characters",
        "Unclassified dimension has metadata",
        "Classified dimension requires a value and source",
        "Required field missing",
        "Unknown field",
        "Unsupported value",
        "Expected text",
        "Expected an object",
        "Invalid JSON",
        "Invalid input",
    }
)
_REASONS = {
    "missing": "Required field missing",
    "extra_forbidden": "Unknown field",
    "literal_error": "Unsupported value",
    "string_type": "Expected text",
    "model_type": "Expected an object",
    "json_invalid": "Invalid JSON",
}


def _valid_database_text(value: str) -> str:
    if "\x00" in value or any("\ud800" <= char <= "\udfff" for char in value):
        raise ValueError("Text contains unsupported characters")
    return value


def _safe_validation_error(title: str, error: ValidationError) -> ValidationError:
    errors: list[InitErrorDetails] = []
    for item in error.errors(include_input=False, include_url=False):
        reason = _REASONS.get(item["type"], "Invalid input")
        if item["type"] == "value_error":
            message = str(item.get("ctx", {}).get("error", ""))
            if message in _SAFE_REASONS:
                reason = message
        elif item["type"] == "enrichment_validation" and item["msg"] in _SAFE_REASONS:
            reason = item["msg"]
        location = tuple(
            part if isinstance(part, str) and part in _SAFE_FIELDS else "unknown_field"
            for part in item["loc"]
        )
        errors.append(
            {
                "type": PydanticCustomError(
                    "enrichment_validation", "{reason}", {"reason": reason}
                ),
                "loc": location,
                "input": None,
            }
        )
    return ValidationError.from_exception_data(title, errors)


class _SafeValidationModel(BaseModel):
    """Prevent validation errors from carrying enrichment payloads."""

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source: object, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        schema = handler(source)

        def validate(
            value: object, inner: core_schema.ValidatorFunctionWrapHandler
        ) -> object:
            try:
                return inner(value)
            except ValidationError as error:
                sanitized = _safe_validation_error(cls.__name__, error)
            raise sanitized from None

        return core_schema.no_info_wrap_validator_function(validate, schema)

    @classmethod
    def model_validate_json(
        cls,
        json_data: str | bytes | bytearray,
        *,
        strict: bool | None = None,
        extra: ExtraValues | None = None,
        context: object | None = None,
        by_alias: bool | None = None,
        by_name: bool | None = None,
    ) -> Self:
        try:
            return super().model_validate_json(
                json_data,
                strict=strict,
                extra=extra,
                context=context,
                by_alias=by_alias,
                by_name=by_name,
            )
        except ValidationError as error:
            sanitized = _safe_validation_error(cls.__name__, error)
        raise sanitized from None


class ClassificationInput(_SafeValidationModel):
    """A complete replacement for one classification and its provenance."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    value: str
    status: Status
    source: Source
    confidence: str | None = None

    @field_validator("value")
    @classmethod
    def valid_value_text(cls, value: str) -> str:
        return _valid_database_text(value)

    @field_validator("confidence")
    @classmethod
    def valid_confidence(cls, value: str | None) -> str | None:
        if value is not None and (
            re.fullmatch(r"(?:0|[1-9][0-9]{0,2})(?:\.[0-9]{1,2})?", value) is None
            or Decimal(value) > 100
        ):
            raise ValueError("Invalid confidence percentage")
        return value


class EnrichmentUpdate(_SafeValidationModel):
    """Partial patch: omitted fields remain unchanged; null clears a field."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    transaction_type: ClassificationInput | None = None
    category: ClassificationInput | None = None
    budget_treatment: ClassificationInput | None = None
    user_annotation: str | None = None
    user_explanation: str | None = None
    ai_explanation: str | None = None

    @field_validator("user_annotation", "user_explanation", "ai_explanation")
    @classmethod
    def valid_context_text(cls, value: str | None) -> str | None:
        return _valid_database_text(value) if value is not None else None

    @model_validator(mode="after")
    def valid_patch(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("An enrichment update must not be empty")
        if self.transaction_type and self.transaction_type.value not in {
            "expense",
            "income",
            "transfer",
            "refund",
        }:
            raise ValueError("Invalid transaction type")
        if self.budget_treatment and self.budget_treatment.value not in {
            "ordinary",
            "extraordinary",
            "excluded",
        }:
            raise ValueError("Invalid budget treatment")
        if self.category and not self.category.value.strip():
            raise ValueError("Invalid category")
        return self


class ClassificationResult(_SafeValidationModel):
    value: str | None = None
    status: Literal["unclassified", "provisional", "confirmed"] = "unclassified"
    source: Source | None = None
    confidence: str | None = None

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.status == "unclassified":
            if (
                self.value is not None
                or self.source is not None
                or self.confidence is not None
            ):
                raise ValueError("Unclassified dimension has metadata")
        else:
            if self.value is None or not self.value.strip() or self.source is None:
                raise ValueError("Classified dimension requires a value and source")
            ClassificationInput(
                value=self.value,
                status=self.status,
                source=self.source,
                confidence=self.confidence,
            )
        return self


class EnrichmentResult(_SafeValidationModel):
    transaction_type: ClassificationResult = ClassificationResult()
    category: ClassificationResult = ClassificationResult()
    budget_treatment: ClassificationResult = ClassificationResult()
    user_annotation: str | None = None
    user_explanation: str | None = None
    ai_explanation: str | None = None

    @model_validator(mode="after")
    def valid_dimensions(self) -> Self:
        if (
            self.transaction_type.value is not None
            and self.transaction_type.value
            not in {"expense", "income", "transfer", "refund"}
        ):
            raise ValueError("Invalid transaction type")
        if (
            self.budget_treatment.value is not None
            and self.budget_treatment.value
            not in {"ordinary", "extraordinary", "excluded"}
        ):
            raise ValueError("Invalid budget treatment")
        return self


class OccurrenceNotFound(Exception):
    """The requested occurrence does not exist."""


class EnrichmentStorageError(Exception):
    """The update failed without committing."""


class EnrichmentLockTimeout(EnrichmentStorageError):
    """The occurrence could not be locked within five seconds."""


class EnrichmentCommitUnknown(Exception):
    """Commit outcome is unknown; read current state before retrying."""


def build_result(
    classifications: list[TransactionClassification], context: TransactionContext | None
) -> EnrichmentResult:
    """Materialize missing dimensions without inferring classification."""
    data: dict[str, object] = {}
    for row in classifications:
        data[row.dimension] = ClassificationResult.model_validate(
            {
                "value": row.value,
                "status": row.status,
                "source": row.source,
                "confidence": str(row.confidence)
                if row.confidence is not None
                else None,
            }
        )
    if context is not None:
        data.update({field: getattr(context, field) for field in CONTEXT_FIELDS})
    return EnrichmentResult.model_validate(data)


async def _rollback(session: AsyncSession) -> None:
    try:
        await session.rollback()
    except SQLAlchemyError, OSError:
        raise EnrichmentStorageError(
            "Could not roll back transaction enrichment"
        ) from None


async def lock_occurrence(
    session: AsyncSession, occurrence_id: int
) -> TransactionOccurrence:
    """Lock an occurrence in the caller's transaction; the caller sets lock timeout."""
    occurrence = await session.scalar(
        select(TransactionOccurrence)
        .where(TransactionOccurrence.id == occurrence_id)
        .with_for_update()
    )
    if occurrence is None:
        raise OccurrenceNotFound("Transaction occurrence not found")
    return occurrence


async def apply_enrichment_in_session(
    session: AsyncSession, occurrence_id: int, update: EnrichmentUpdate
) -> EnrichmentResult:
    """Apply a patch under the occurrence lock without committing the caller's transaction.

    The caller owns the session, lock timeout, commit, rollback and error handling.
    """
    update = EnrichmentUpdate.model_validate(update.model_dump(exclude_unset=True))
    await lock_occurrence(session, occurrence_id)
    for dimension in DIMENSIONS:
        if dimension not in update.model_fields_set:
            continue
        value = getattr(update, dimension)
        existing = await session.get(
            TransactionClassification, (occurrence_id, dimension)
        )
        if value is None:
            if existing is not None:
                await session.delete(existing)
        elif existing is None:
            session.add(
                TransactionClassification(
                    occurrence_id=occurrence_id,
                    dimension=dimension,
                    value=value.value,
                    status=value.status,
                    source=value.source,
                    confidence=Decimal(value.confidence)
                    if value.confidence is not None
                    else None,
                )
            )
        else:
            existing.value = value.value
            existing.status = value.status
            existing.source = value.source
            existing.confidence = (
                Decimal(value.confidence) if value.confidence is not None else None
            )
    if update.model_fields_set.intersection(CONTEXT_FIELDS):
        context = await session.get(TransactionContext, occurrence_id)
        if context is None:
            context = TransactionContext(occurrence_id=occurrence_id)
            session.add(context)
        for field in CONTEXT_FIELDS:
            if field in update.model_fields_set:
                setattr(context, field, getattr(update, field))
    await session.flush()
    rows = list(
        (
            await session.scalars(
                select(TransactionClassification).where(
                    TransactionClassification.occurrence_id == occurrence_id
                )
            )
        ).all()
    )
    context = await session.get(TransactionContext, occurrence_id)
    return build_result(rows, context)


async def update_enrichment(
    engine: AsyncEngine, occurrence_id: int, update: EnrichmentUpdate
) -> EnrichmentResult:
    """Atomically apply a validated patch; read state before retrying an unknown commit."""
    update = EnrichmentUpdate.model_validate(update.model_dump(exclude_unset=True))
    async with AsyncSession(engine, expire_on_commit=False) as session:
        try:
            await session.execute(text("SET LOCAL lock_timeout = '5s'"))
            result = await apply_enrichment_in_session(session, occurrence_id, update)
        except asyncio.CancelledError:
            await _rollback(session)
            raise
        except OccurrenceNotFound:
            await _rollback(session)
            raise
        except (SQLAlchemyError, OSError) as exc:
            await _rollback(session)
            if (
                isinstance(exc, DBAPIError)
                and getattr(exc.orig, "sqlstate", None) == "55P03"
            ):
                raise EnrichmentLockTimeout(
                    "Timed out waiting for transaction lock"
                ) from None
            raise EnrichmentStorageError(
                "Could not update transaction enrichment"
            ) from None
        try:
            await session.commit()
        except SQLAlchemyError, OSError, asyncio.CancelledError:
            raise EnrichmentCommitUnknown(
                "Commit outcome unknown; read current state before retrying"
            ) from None
        return result
