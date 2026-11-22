"""Persistence schema for bank-export provenance and occurrences."""

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SelectedAccount(Base):
    __tablename__ = "selected_account"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    account_reference: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    display_label: Mapped[str | None] = mapped_column(Text)


class SourceFile(Base):
    __tablename__ = "source_file"
    __table_args__ = (
        CheckConstraint("transaction_row_count >= 0", name="ck_source_row_count"),
        CheckConstraint(
            "account_id IS NOT NULL OR transaction_row_count = 0",
            name="ck_source_account_or_empty",
        ),
    )

    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    transaction_row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("selected_account.id"))


class TransactionObservation(Base):
    __tablename__ = "transaction_observation"
    __table_args__ = (
        UniqueConstraint("source_file_sha256", "sheet_index", "row_number"),
        CheckConstraint(
            "sheet_index >= 0 AND row_number >= 1", name="ck_source_location"
        ),
        CheckConstraint("occurrence_ordinal >= 1", name="ck_occurrence_ordinal"),
        CheckConstraint("currency = 'EUR'", name="ck_observation_currency"),
        CheckConstraint(
            "booking_status IN ('pending', 'booked')", name="ck_observation_status"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_file_sha256: Mapped[str] = mapped_column(
        ForeignKey("source_file.sha256"), nullable=False
    )
    sheet_index: Mapped[int] = mapped_column(Integer, nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("selected_account.id"), nullable=False
    )
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    operation: Mapped[str | None] = mapped_column(Text)
    details: Mapped[str | None] = mapped_column(Text)
    booking_status: Mapped[str] = mapped_column(String(7), nullable=False)
    category: Mapped[str | None] = mapped_column(Text)
    candidate_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    occurrence_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)


class TransactionOccurrence(Base):
    __tablename__ = "transaction_occurrence"
    __table_args__ = (
        CheckConstraint("currency = 'EUR'", name="ck_occurrence_currency"),
        CheckConstraint(
            "booking_status IN ('pending', 'booked')", name="ck_occurrence_status"
        ),
        CheckConstraint(
            "reconciliation_state IN ('confirmed', 'unresolved', 'pending-only')",
            name="ck_reconciliation_state",
        ),
        CheckConstraint(
            "booking_status IS NOT NULL OR reconciliation_state = 'unresolved'",
            name="ck_unknown_status_unresolved",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("selected_account.id"), nullable=False
    )
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    booking_status: Mapped[str | None] = mapped_column(String(7))
    reconciliation_state: Mapped[str] = mapped_column(String(12), nullable=False)

    @property
    def is_ongoing_expense(self) -> bool:
        """Only pending debits are ongoing expenses."""
        return (
            self.booking_status == "pending"
            and self.reconciliation_state != "unresolved"
            and self.amount_minor < 0
        )


occurrence_observation = Table(
    "occurrence_observation",
    Base.metadata,
    Column(
        "occurrence_id",
        BigInteger,
        ForeignKey("transaction_occurrence.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "observation_id",
        BigInteger,
        ForeignKey("transaction_observation.id"),
        primary_key=True,
    ),
)
