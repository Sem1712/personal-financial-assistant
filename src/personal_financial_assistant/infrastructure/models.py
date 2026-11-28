"""Persistence schema for bank-export provenance and occurrences."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
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


class UIImportRun(Base):
    """Durable, non-sensitive status of one UI-initiated import."""

    __tablename__ = "ui_import_run"
    __table_args__ = (
        CheckConstraint(
            "state IN ('running', 'succeeded', 'no_files', 'failed', 'unknown')",
            name="ck_ui_import_run_state",
        ),
        CheckConstraint(
            "(state = 'running' AND finished_at IS NULL) OR "
            "(state <> 'running' AND finished_at IS NOT NULL)",
            name="ck_ui_import_run_finished",
        ),
        CheckConstraint(
            "(state = 'failed' AND error_code IS NOT NULL AND error_message IS NOT NULL) "
            "OR (state <> 'failed' AND error_code IS NULL AND error_message IS NULL)",
            name="ck_ui_import_run_error",
        ),
        *(
            CheckConstraint(f"{name} >= 0", name=f"ck_ui_import_run_{name}")
            for name in (
                "files_seen",
                "files_processed",
                "files_unchanged",
                "rows_read",
                "transactions_added",
                "transactions_updated",
                "observations_unchanged",
                "unresolved_observations",
            )
        ),
        CheckConstraint(
            "(state IN ('succeeded', 'no_files') AND "
            "files_seen IS NOT NULL AND files_processed IS NOT NULL AND "
            "files_unchanged IS NOT NULL AND rows_read IS NOT NULL AND "
            "transactions_added IS NOT NULL AND transactions_updated IS NOT NULL AND "
            "observations_unchanged IS NOT NULL AND unresolved_observations IS NOT NULL) "
            "OR (state NOT IN ('succeeded', 'no_files') AND "
            "files_seen IS NULL AND files_processed IS NULL AND "
            "files_unchanged IS NULL AND rows_read IS NULL AND "
            "transactions_added IS NULL AND transactions_updated IS NULL AND "
            "observations_unchanged IS NULL AND unresolved_observations IS NULL)",
            name="ck_ui_import_run_counts",
        ),
        Index("ix_ui_import_run_latest", "started_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    state: Mapped[str] = mapped_column(String(10), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    files_seen: Mapped[int | None] = mapped_column(BigInteger)
    files_processed: Mapped[int | None] = mapped_column(BigInteger)
    files_unchanged: Mapped[int | None] = mapped_column(BigInteger)
    rows_read: Mapped[int | None] = mapped_column(BigInteger)
    transactions_added: Mapped[int | None] = mapped_column(BigInteger)
    transactions_updated: Mapped[int | None] = mapped_column(BigInteger)
    observations_unchanged: Mapped[int | None] = mapped_column(BigInteger)
    unresolved_observations: Mapped[int | None] = mapped_column(BigInteger)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)


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


class TransactionClassification(Base):
    """Current classification and its provenance for one occurrence dimension."""

    __tablename__ = "transaction_classification"
    __table_args__ = (
        CheckConstraint(
            "dimension IN ('transaction_type', 'category', 'budget_treatment')",
            name="ck_classification_dimension",
        ),
        # Match Python str.strip() and the detail view's Unicode whitespace set.
        CheckConstraint(
            "(dimension = 'transaction_type' AND value IN ('expense', 'income', 'transfer', 'refund')) OR "
            "(dimension = 'budget_treatment' AND value IN ('ordinary', 'extraordinary', 'excluded')) OR "
            r"(dimension = 'category' AND value ~ U&'[^\0009-\000D\001C-\0020\0085\00A0\1680\2000-\200A\2028\2029\202F\205F\3000]')",
            name="ck_classification_value",
        ),
        CheckConstraint(
            "status IN ('provisional', 'confirmed')", name="ck_classification_status"
        ),
        CheckConstraint(
            "source IN ('ai', 'rule', 'user')", name="ck_classification_source"
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 100 "
            "AND scale(confidence) <= 2)",
            name="ck_classification_confidence",
        ),
    )

    occurrence_id: Mapped[int] = mapped_column(
        ForeignKey("transaction_occurrence.id", ondelete="RESTRICT"), primary_key=True
    )
    dimension: Mapped[str] = mapped_column(String(16), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(11), nullable=False)
    source: Mapped[str] = mapped_column(String(4), nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric)


class TransactionContext(Base):
    """Optional user and AI context associated with one occurrence."""

    __tablename__ = "transaction_context"

    occurrence_id: Mapped[int] = mapped_column(
        ForeignKey("transaction_occurrence.id", ondelete="RESTRICT"), primary_key=True
    )
    user_annotation: Mapped[str | None] = mapped_column(Text)
    user_explanation: Mapped[str | None] = mapped_column(Text)
    ai_explanation: Mapped[str | None] = mapped_column(Text)


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
