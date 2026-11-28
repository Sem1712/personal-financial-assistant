"""Persistence schema for bank-export provenance and occurrences."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


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


_NON_WHITESPACE = r"~ U&'[^\0009-\000D\001C-\0020\0085\00A0\1680\2000-\200A\2028\2029\202F\205F\3000]'"


class Merchant(Base):
    """Canonical local merchant, independent of imported observations."""

    __tablename__ = "merchant"
    __table_args__ = (
        CheckConstraint(f"canonical_name {_NON_WHITESPACE}", name="ck_merchant_name"),
        CheckConstraint("revision >= 1", name="ck_merchant_revision"),
        CheckConstraint("enabled_revision >= 1", name="ck_merchant_enabled_revision"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    revision: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("1")
    )
    enabled_revision: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("1")
    )


class MerchantMatch(Base):
    """Literal alias or contained-text match for a merchant."""

    __tablename__ = "merchant_match"
    __table_args__ = (
        UniqueConstraint("merchant_id", "kind", "normalized_text"),
        CheckConstraint(
            "kind IN ('alias', 'substring')", name="ck_merchant_match_kind"
        ),
        CheckConstraint(
            f"original_text {_NON_WHITESPACE}", name="ck_merchant_match_original"
        ),
        CheckConstraint(
            f"normalized_text {_NON_WHITESPACE}", name="ck_merchant_match_normalized"
        ),
        CheckConstraint(
            "origin IN ('user', 'ai', 'service')", name="ck_merchant_match_origin"
        ),
        CheckConstraint("revision >= 1", name="ck_merchant_match_revision"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    merchant_id: Mapped[int] = mapped_column(
        ForeignKey("merchant.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(9), nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    origin: Mapped[str] = mapped_column(String(7), nullable=False)
    confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    revision: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("1")
    )


class MerchantDefault(Base):
    """Current merchant category default, including disabled defaults."""

    __tablename__ = "merchant_default"
    __table_args__ = (
        CheckConstraint(
            f"category {_NON_WHITESPACE}", name="ck_merchant_default_category"
        ),
        CheckConstraint(
            "origin IN ('user', 'ai', 'service')", name="ck_merchant_default_origin"
        ),
        CheckConstraint("revision >= 1", name="ck_merchant_default_revision"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    merchant_id: Mapped[int] = mapped_column(
        ForeignKey("merchant.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    category: Mapped[str] = mapped_column(Text, nullable=False)
    origin: Mapped[str] = mapped_column(String(7), nullable=False)
    confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    revision: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("1")
    )


class ClassificationPreference(Base):
    """Reusable merchant or literal-description category preference."""

    __tablename__ = "classification_preference"
    __table_args__ = (
        CheckConstraint(
            "(match_kind = 'merchant' AND merchant_id IS NOT NULL AND match_text IS NULL) OR "
            "(match_kind IN ('exact_description', 'substring_description') "
            f"AND merchant_id IS NULL AND match_text IS NOT NULL AND match_text {_NON_WHITESPACE})",
            name="ck_preference_operand",
        ),
        CheckConstraint(f"category {_NON_WHITESPACE}", name="ck_preference_category"),
        CheckConstraint(
            "origin IN ('user', 'ai', 'service')", name="ck_preference_origin"
        ),
        CheckConstraint("revision >= 1", name="ck_preference_revision"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    match_kind: Mapped[str] = mapped_column(String(21), nullable=False)
    merchant_id: Mapped[int | None] = mapped_column(
        ForeignKey("merchant.id", ondelete="RESTRICT")
    )
    match_text: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    origin: Mapped[str] = mapped_column(String(7), nullable=False)
    confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    revision: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("1")
    )


class TransactionOverride(Base):
    """Explicit category override for one occurrence."""

    __tablename__ = "transaction_override"
    __table_args__ = (
        CheckConstraint(f"category {_NON_WHITESPACE}", name="ck_override_category"),
        CheckConstraint("revision >= 1", name="ck_override_revision"),
    )

    occurrence_id: Mapped[int] = mapped_column(
        ForeignKey("transaction_occurrence.id", ondelete="RESTRICT"), primary_key=True
    )
    category: Mapped[str] = mapped_column(Text, nullable=False)
    revision: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("1")
    )


class ChangeSuggestion(Base):
    """Pending AI modification of a protected rule or merchant."""

    __tablename__ = "change_suggestion"
    __table_args__ = (
        CheckConstraint(
            "(target_kind = 'merchant' AND target_merchant_id IS NOT NULL AND "
            "target_match_id IS NULL AND target_default_id IS NULL AND target_preference_id IS NULL) OR "
            "(target_kind = 'matching_entry' AND target_merchant_id IS NULL AND "
            "target_match_id IS NOT NULL AND target_default_id IS NULL AND target_preference_id IS NULL) OR "
            "(target_kind = 'merchant_default' AND target_merchant_id IS NULL AND "
            "target_match_id IS NULL AND target_default_id IS NOT NULL AND target_preference_id IS NULL) OR "
            "(target_kind = 'classification_preference' AND target_merchant_id IS NULL AND "
            "target_match_id IS NULL AND target_default_id IS NULL AND target_preference_id IS NOT NULL)",
            name="ck_suggestion_target",
        ),
        CheckConstraint("target_revision >= 1", name="ck_suggestion_revision"),
        CheckConstraint("action IN ('edit', 'disable')", name="ck_suggestion_action"),
        CheckConstraint("origin = 'ai'", name="ck_suggestion_origin"),
        CheckConstraint(
            "state IN ('pending', 'approved', 'rejected', 'stale')",
            name="ck_suggestion_state",
        ),
        CheckConstraint(
            "jsonb_typeof(payload) = 'object'", name="ck_suggestion_payload"
        ),
        CheckConstraint(
            "review_snapshot IS NULL OR jsonb_typeof(review_snapshot) = 'object'",
            name="ck_suggestion_snapshot",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    target_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    target_merchant_id: Mapped[int | None] = mapped_column(
        ForeignKey("merchant.id", ondelete="RESTRICT")
    )
    target_match_id: Mapped[int | None] = mapped_column(
        ForeignKey("merchant_match.id", ondelete="RESTRICT")
    )
    target_default_id: Mapped[int | None] = mapped_column(
        ForeignKey("merchant_default.id", ondelete="RESTRICT")
    )
    target_preference_id: Mapped[int | None] = mapped_column(
        ForeignKey("classification_preference.id", ondelete="RESTRICT")
    )
    target_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(String(7), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    origin: Mapped[str] = mapped_column(String(2), nullable=False)
    state: Mapped[str] = mapped_column(String(8), nullable=False)
    review_snapshot: Mapped[dict[str, object] | None] = mapped_column(
        JSONB(none_as_null=True)
    )


def _entry_reference_check(prefix: str) -> str:
    return (
        f"({prefix}_kind = 'matching_entry' AND {prefix}_match_id IS NOT NULL AND "
        f"{prefix}_default_id IS NULL AND {prefix}_preference_id IS NULL) OR "
        f"({prefix}_kind = 'merchant_default' AND {prefix}_match_id IS NULL AND "
        f"{prefix}_default_id IS NOT NULL AND {prefix}_preference_id IS NULL) OR "
        f"({prefix}_kind = 'classification_preference' AND {prefix}_match_id IS NULL AND "
        f"{prefix}_default_id IS NULL AND {prefix}_preference_id IS NOT NULL)"
    )


class ApplicationConflict(Base):
    """A typed AI-versus-confirmed rule conflict on a single occurrence."""

    __tablename__ = "application_conflict"
    __table_args__ = (
        CheckConstraint(_entry_reference_check("ai"), name="ck_conflict_ai_reference"),
        CheckConstraint(
            _entry_reference_check("confirmed"), name="ck_conflict_confirmed_reference"
        ),
        CheckConstraint(
            "(outcome_kind = 'merchant' AND ai_kind = 'matching_entry' "
            "AND confirmed_kind = 'matching_entry') OR "
            "(outcome_kind = 'category' AND ai_kind IN ('merchant_default', 'classification_preference') "
            "AND confirmed_kind IN ('merchant_default', 'classification_preference'))",
            name="ck_conflict_outcome",
        ),
        CheckConstraint(
            "ai_revision >= 1 AND confirmed_revision >= 1 AND evidence_revision >= 1",
            name="ck_conflict_revisions",
        ),
        CheckConstraint(
            "state IN ('pending', 'approved', 'rejected', 'stale')",
            name="ck_conflict_state",
        ),
        CheckConstraint(
            "review_snapshot IS NULL OR jsonb_typeof(review_snapshot) = 'object'",
            name="ck_conflict_snapshot",
        ),
        UniqueConstraint(
            "occurrence_id",
            "ai_kind",
            "ai_match_id",
            "ai_default_id",
            "ai_preference_id",
            "confirmed_kind",
            "confirmed_match_id",
            "confirmed_default_id",
            "confirmed_preference_id",
            postgresql_nulls_not_distinct=True,
            name="uq_conflict_occurrence_entries",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    occurrence_id: Mapped[int] = mapped_column(
        ForeignKey("transaction_occurrence.id", ondelete="RESTRICT"), nullable=False
    )
    ai_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    ai_match_id: Mapped[int | None] = mapped_column(
        ForeignKey("merchant_match.id", ondelete="RESTRICT")
    )
    ai_default_id: Mapped[int | None] = mapped_column(
        ForeignKey("merchant_default.id", ondelete="RESTRICT")
    )
    ai_preference_id: Mapped[int | None] = mapped_column(
        ForeignKey("classification_preference.id", ondelete="RESTRICT")
    )
    ai_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    confirmed_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    confirmed_match_id: Mapped[int | None] = mapped_column(
        ForeignKey("merchant_match.id", ondelete="RESTRICT")
    )
    confirmed_default_id: Mapped[int | None] = mapped_column(
        ForeignKey("merchant_default.id", ondelete="RESTRICT")
    )
    confirmed_preference_id: Mapped[int | None] = mapped_column(
        ForeignKey("classification_preference.id", ondelete="RESTRICT")
    )
    confirmed_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    evidence_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    outcome_kind: Mapped[str] = mapped_column(String(8), nullable=False)
    state: Mapped[str] = mapped_column(String(8), nullable=False)
    review_snapshot: Mapped[dict[str, object] | None] = mapped_column(
        JSONB(none_as_null=True)
    )


class ApplicationApproval(Base):
    """Explicit approval scoped to a conflict's reviewed revisions."""

    __tablename__ = "application_approval"
    __table_args__ = (
        CheckConstraint(
            "ai_revision >= 1 AND confirmed_revision >= 1 AND evidence_revision >= 1",
            name="ck_approval_revisions",
        ),
        CheckConstraint(
            "jsonb_typeof(merchant_revisions) = 'array'",
            name="ck_approval_merchant_revisions",
        ),
    )

    conflict_id: Mapped[int] = mapped_column(
        ForeignKey("application_conflict.id", ondelete="RESTRICT"), primary_key=True
    )
    ai_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    confirmed_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    evidence_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    merchant_revisions: Mapped[list[list[int]]] = mapped_column(JSONB, nullable=False)


class RulesConfiguration(Base):
    """Singleton row used to serialize rule changes, reviews and evaluations."""

    __tablename__ = "rules_configuration"
    __table_args__ = (CheckConstraint("id = 1", name="ck_rules_configuration_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)


class OccurrenceEvidenceRevision(Base):
    """Revision of the observations linked to an occurrence."""

    __tablename__ = "occurrence_evidence_revision"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="ck_evidence_revision_positive"),
    )

    occurrence_id: Mapped[int] = mapped_column(
        ForeignKey("transaction_occurrence.id", ondelete="RESTRICT"), primary_key=True
    )
    revision: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("1")
    )


class RuleEvaluationWork(Base):
    """Durable automatic evaluation work created in the import transaction."""

    __tablename__ = "rule_evaluation_work"
    __table_args__ = (
        CheckConstraint(
            "(state IN ('pending', 'completed') AND last_error_code IS NULL) OR "
            "(state = 'failed' AND last_error_code IS NOT NULL)",
            name="ck_evaluation_work_state",
        ),
        CheckConstraint(
            "last_error_code IS NULL OR last_error_code ~ '^[a-z][a-z0-9_]{0,63}$'",
            name="ck_evaluation_work_error_code",
        ),
        Index("ix_evaluation_work_correlation", "import_correlation_id"),
    )

    occurrence_id: Mapped[int] = mapped_column(
        ForeignKey("transaction_occurrence.id", ondelete="RESTRICT"), primary_key=True
    )
    import_correlation_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    state: Mapped[str] = mapped_column(String(9), nullable=False)
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    latest_result: Mapped[RuleEvaluationOutcome | None] = relationship(
        back_populates="work", lazy="raise"
    )


class RuleEvaluationOutcome(Base):
    """Latest completed automatic evaluation, including its explainable decisions."""

    __tablename__ = "rule_evaluation_outcome"
    __table_args__ = (
        CheckConstraint("evidence_revision >= 1", name="ck_outcome_evidence_revision"),
        CheckConstraint(
            "(merchant_status = 'resolved' AND merchant_id IS NOT NULL) OR "
            "(merchant_status IN ('no_match', 'conflict') AND merchant_id IS NULL)",
            name="ck_outcome_merchant",
        ),
        CheckConstraint(
            "jsonb_typeof(matching_candidates) = 'array' "
            "AND jsonb_typeof(category_decision) = 'object' "
            "AND jsonb_typeof(winning_references) = 'array' "
            "AND jsonb_typeof(blocked_ai_conflicts) = 'array'",
            name="ck_outcome_json_shapes",
        ),
        CheckConstraint(
            "(merchant_decision IS NULL OR jsonb_typeof(merchant_decision) = 'object') "
            "AND (category_conflict_candidates IS NULL OR "
            "jsonb_typeof(category_conflict_candidates) = 'array')",
            name="ck_outcome_explanation_shapes",
        ),
    )

    occurrence_id: Mapped[int] = mapped_column(
        ForeignKey("rule_evaluation_work.occurrence_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    evidence_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    merchant_status: Mapped[str] = mapped_column(String(8), nullable=False)
    merchant_id: Mapped[int | None] = mapped_column(
        ForeignKey("merchant.id", ondelete="RESTRICT")
    )
    matching_candidates: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False
    )
    category_decision: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    winning_references: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False
    )
    blocked_ai_conflicts: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False
    )
    merchant_decision: Mapped[dict[str, object] | None] = mapped_column(
        JSONB(none_as_null=True)
    )
    category_conflict_candidates: Mapped[list[dict[str, object]] | None] = (
        mapped_column(JSONB(none_as_null=True))
    )
    work: Mapped[RuleEvaluationWork] = relationship(
        back_populates="latest_result", lazy="raise"
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
