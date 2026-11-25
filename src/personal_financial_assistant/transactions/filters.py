"""Validate transaction filters and bind pagination cursors to their filters."""

import base64
import binascii
import hashlib
import hmac
import json
import re
from datetime import date
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)


class CategoryValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["value"]
    value: str

    @field_validator("value")
    @classmethod
    def valid_value(cls, value: str) -> str:
        if not value.strip() or "\0" in value:
            raise ValueError("Invalid category")
        return value


class NoRecordedCategory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["no_recorded_category"]


Category = Annotated[CategoryValue | NoRecordedCategory, Field(discriminator="kind")]


class _Cursor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    id: int = Field(strict=True, ge=1, le=2**63 - 1)
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


def _minor_units(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(
        r"[+]?(?:[0-9]+(?:\.[0-9]{0,2})?|\.[0-9]{1,2})", value
    ):
        raise ValueError("Invalid nonnegative EUR amount")
    unsigned = value.lstrip("+")
    whole, _, fraction = unsigned.partition(".")
    whole = whole.lstrip("0") or "0"
    if len(whole) > 17:
        raise ValueError("EUR amount out of range")
    result = int(whole) * 100 + int(fraction.ljust(2, "0"))
    if result > 2**63:
        raise ValueError("EUR amount out of range")
    return result


class TransactionFilters(BaseModel):
    """Validated filters with exact absolute EUR-cent bounds and signed direction."""

    model_config = ConfigDict(extra="forbid")

    date_from: date | None = None
    date_to: date | None = None
    booking_status: Literal["pending", "booked", "unknown"] | None = None
    text: str | None = None
    category: Category | None = None
    amount_min: int | None = None
    amount_max: int | None = None
    direction: Literal["withdrawals", "deposits"] | None = None
    cursor: str | None = Field(default=None, max_length=1024)
    page_size: int = Field(default=100, strict=True, ge=1, le=100)

    @field_validator("date_from", "date_to", mode="before")
    @classmethod
    def valid_date(cls, value: object) -> date | None:
        if value is None:
            return None
        if not isinstance(value, str) or not re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value
        ):
            raise ValueError("Invalid date")
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            raise ValueError("Invalid date") from None
        if parsed.isoformat() != value:
            raise ValueError("Invalid date")
        return parsed

    @field_validator("amount_min", "amount_max", mode="before")
    @classmethod
    def valid_amount(cls, value: object) -> int | None:
        return _minor_units(value)

    @field_validator("text")
    @classmethod
    def valid_text(cls, value: str | None) -> str | None:
        if value is not None and "\0" in value:
            raise ValueError("Invalid description")
        return value

    @model_validator(mode="after")
    def valid_ranges_and_cursor(self) -> Self:
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("End date must not precede start date")
        if (
            self.amount_min is not None
            and self.amount_max is not None
            and self.amount_min > self.amount_max
        ):
            raise ValueError("Maximum amount must not be less than minimum amount")
        if self.cursor is not None:
            self.cursor_position()
        return self

    def _fingerprint(self) -> str:
        values = self.model_dump(mode="json", exclude={"cursor", "page_size"})
        encoded = json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    def encode_cursor(self, position_date: date, occurrence_id: int) -> str:
        """Create an opaque cursor for this filter set."""
        cursor = _Cursor(
            date=position_date, id=occurrence_id, fingerprint=self._fingerprint()
        )
        return (
            base64.urlsafe_b64encode(cursor.model_dump_json().encode())
            .decode()
            .rstrip("=")
        )

    def cursor_position(self) -> tuple[date, int] | None:
        """Return the cursor position, rejecting invalid or mismatched filters."""
        if self.cursor is None:
            return None
        try:
            if not re.fullmatch(r"[A-Za-z0-9_-]+", self.cursor):
                raise ValueError("Invalid cursor")
            raw = base64.b64decode(
                self.cursor + "=" * (-len(self.cursor) % 4),
                altchars=b"-_",
                validate=True,
            )
            cursor = _Cursor.model_validate_json(raw)
        except binascii.Error, ValidationError, ValueError:
            raise ValueError("Invalid cursor") from None
        if not hmac.compare_digest(cursor.fingerprint, self._fingerprint()):
            raise ValueError("Cursor does not match filters")
        return cursor.date, cursor.id
