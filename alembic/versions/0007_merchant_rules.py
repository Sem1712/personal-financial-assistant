"""Add merchant rules, review records and durable evaluation work.

Revision ID: 0007_merchant_rules
Revises: 0006_category_whitespace
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0007_merchant_rules"
down_revision = "0006_category_whitespace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "merchant",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column(
            "enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "revision", sa.BigInteger(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column(
            "enabled_revision",
            sa.BigInteger(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "canonical_name ~ U&'[^\\0009-\\000D\\001C-\\0020\\0085\\00A0\\1680\\2000-\\200A\\2028\\2029\\202F\\205F\\3000]'",
            name="ck_merchant_name",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_merchant_revision"),
        sa.CheckConstraint(
            "enabled_revision >= 1", name="ck_merchant_enabled_revision"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "rules_configuration",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.CheckConstraint("id = 1", name="ck_rules_configuration_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "classification_preference",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("match_kind", sa.String(length=21), nullable=False),
        sa.Column("merchant_id", sa.BigInteger(), nullable=True),
        sa.Column("match_text", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("origin", sa.String(length=7), nullable=False),
        sa.Column(
            "confirmed", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "revision", sa.BigInteger(), server_default=sa.text("1"), nullable=False
        ),
        sa.CheckConstraint(
            "(match_kind = 'merchant' AND merchant_id IS NOT NULL AND match_text IS NULL) OR (match_kind IN ('exact_description', 'substring_description') AND merchant_id IS NULL AND match_text IS NOT NULL AND match_text ~ U&'[^\\0009-\\000D\\001C-\\0020\\0085\\00A0\\1680\\2000-\\200A\\2028\\2029\\202F\\205F\\3000]')",
            name="ck_preference_operand",
        ),
        sa.CheckConstraint(
            "category ~ U&'[^\\0009-\\000D\\001C-\\0020\\0085\\00A0\\1680\\2000-\\200A\\2028\\2029\\202F\\205F\\3000]'",
            name="ck_preference_category",
        ),
        sa.CheckConstraint(
            "origin IN ('user', 'ai', 'service')", name="ck_preference_origin"
        ),
        sa.CheckConstraint("revision >= 1", name="ck_preference_revision"),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchant.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "merchant_default",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("merchant_id", sa.BigInteger(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("origin", sa.String(length=7), nullable=False),
        sa.Column(
            "confirmed", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "revision", sa.BigInteger(), server_default=sa.text("1"), nullable=False
        ),
        sa.CheckConstraint(
            "category ~ U&'[^\\0009-\\000D\\001C-\\0020\\0085\\00A0\\1680\\2000-\\200A\\2028\\2029\\202F\\205F\\3000]'",
            name="ck_merchant_default_category",
        ),
        sa.CheckConstraint(
            "origin IN ('user', 'ai', 'service')", name="ck_merchant_default_origin"
        ),
        sa.CheckConstraint("revision >= 1", name="ck_merchant_default_revision"),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchant.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("merchant_id"),
    )
    op.create_table(
        "merchant_match",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("merchant_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=9), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("origin", sa.String(length=7), nullable=False),
        sa.Column(
            "confirmed", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "revision", sa.BigInteger(), server_default=sa.text("1"), nullable=False
        ),
        sa.CheckConstraint(
            "kind IN ('alias', 'substring')", name="ck_merchant_match_kind"
        ),
        sa.CheckConstraint(
            "normalized_text ~ U&'[^\\0009-\\000D\\001C-\\0020\\0085\\00A0\\1680\\2000-\\200A\\2028\\2029\\202F\\205F\\3000]'",
            name="ck_merchant_match_normalized",
        ),
        sa.CheckConstraint(
            "origin IN ('user', 'ai', 'service')", name="ck_merchant_match_origin"
        ),
        sa.CheckConstraint(
            "original_text ~ U&'[^\\0009-\\000D\\001C-\\0020\\0085\\00A0\\1680\\2000-\\200A\\2028\\2029\\202F\\205F\\3000]'",
            name="ck_merchant_match_original",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_merchant_match_revision"),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchant.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("merchant_id", "kind", "normalized_text"),
    )
    op.create_table(
        "application_conflict",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("occurrence_id", sa.BigInteger(), nullable=False),
        sa.Column("ai_kind", sa.String(length=32), nullable=False),
        sa.Column("ai_match_id", sa.BigInteger(), nullable=True),
        sa.Column("ai_default_id", sa.BigInteger(), nullable=True),
        sa.Column("ai_preference_id", sa.BigInteger(), nullable=True),
        sa.Column("ai_revision", sa.BigInteger(), nullable=False),
        sa.Column("confirmed_kind", sa.String(length=32), nullable=False),
        sa.Column("confirmed_match_id", sa.BigInteger(), nullable=True),
        sa.Column("confirmed_default_id", sa.BigInteger(), nullable=True),
        sa.Column("confirmed_preference_id", sa.BigInteger(), nullable=True),
        sa.Column("confirmed_revision", sa.BigInteger(), nullable=False),
        sa.Column("evidence_revision", sa.BigInteger(), nullable=False),
        sa.Column("outcome_kind", sa.String(length=8), nullable=False),
        sa.Column("state", sa.String(length=8), nullable=False),
        sa.Column(
            "review_snapshot",
            postgresql.JSONB(none_as_null=True, astext_type=sa.Text()),
            nullable=True,
        ),
        sa.CheckConstraint(
            "(ai_kind = 'matching_entry' AND ai_match_id IS NOT NULL AND ai_default_id IS NULL AND ai_preference_id IS NULL) OR (ai_kind = 'merchant_default' AND ai_match_id IS NULL AND ai_default_id IS NOT NULL AND ai_preference_id IS NULL) OR (ai_kind = 'classification_preference' AND ai_match_id IS NULL AND ai_default_id IS NULL AND ai_preference_id IS NOT NULL)",
            name="ck_conflict_ai_reference",
        ),
        sa.CheckConstraint(
            "(confirmed_kind = 'matching_entry' AND confirmed_match_id IS NOT NULL AND confirmed_default_id IS NULL AND confirmed_preference_id IS NULL) OR (confirmed_kind = 'merchant_default' AND confirmed_match_id IS NULL AND confirmed_default_id IS NOT NULL AND confirmed_preference_id IS NULL) OR (confirmed_kind = 'classification_preference' AND confirmed_match_id IS NULL AND confirmed_default_id IS NULL AND confirmed_preference_id IS NOT NULL)",
            name="ck_conflict_confirmed_reference",
        ),
        sa.CheckConstraint(
            "(outcome_kind = 'merchant' AND ai_kind = 'matching_entry' AND confirmed_kind = 'matching_entry') OR (outcome_kind = 'category' AND ai_kind IN ('merchant_default', 'classification_preference') AND confirmed_kind IN ('merchant_default', 'classification_preference'))",
            name="ck_conflict_outcome",
        ),
        sa.CheckConstraint(
            "review_snapshot IS NULL OR jsonb_typeof(review_snapshot) = 'object'",
            name="ck_conflict_snapshot",
        ),
        sa.CheckConstraint(
            "state IN ('pending', 'approved', 'rejected', 'stale')",
            name="ck_conflict_state",
        ),
        sa.CheckConstraint(
            "ai_revision >= 1 AND confirmed_revision >= 1 AND evidence_revision >= 1",
            name="ck_conflict_revisions",
        ),
        sa.ForeignKeyConstraint(
            ["ai_default_id"], ["merchant_default.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["ai_match_id"], ["merchant_match.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["ai_preference_id"], ["classification_preference.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_default_id"], ["merchant_default.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_match_id"], ["merchant_match.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_preference_id"],
            ["classification_preference.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["occurrence_id"], ["transaction_occurrence.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "occurrence_id",
            "ai_kind",
            "ai_match_id",
            "ai_default_id",
            "ai_preference_id",
            "confirmed_kind",
            "confirmed_match_id",
            "confirmed_default_id",
            "confirmed_preference_id",
            name="uq_conflict_occurrence_entries",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_table(
        "change_suggestion",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("target_kind", sa.String(length=32), nullable=False),
        sa.Column("target_merchant_id", sa.BigInteger(), nullable=True),
        sa.Column("target_match_id", sa.BigInteger(), nullable=True),
        sa.Column("target_default_id", sa.BigInteger(), nullable=True),
        sa.Column("target_preference_id", sa.BigInteger(), nullable=True),
        sa.Column("target_revision", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(length=7), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("origin", sa.String(length=2), nullable=False),
        sa.Column("state", sa.String(length=8), nullable=False),
        sa.Column(
            "review_snapshot",
            postgresql.JSONB(none_as_null=True, astext_type=sa.Text()),
            nullable=True,
        ),
        sa.CheckConstraint(
            "(target_kind = 'merchant' AND target_merchant_id IS NOT NULL AND target_match_id IS NULL AND target_default_id IS NULL AND target_preference_id IS NULL) OR (target_kind = 'matching_entry' AND target_merchant_id IS NULL AND target_match_id IS NOT NULL AND target_default_id IS NULL AND target_preference_id IS NULL) OR (target_kind = 'merchant_default' AND target_merchant_id IS NULL AND target_match_id IS NULL AND target_default_id IS NOT NULL AND target_preference_id IS NULL) OR (target_kind = 'classification_preference' AND target_merchant_id IS NULL AND target_match_id IS NULL AND target_default_id IS NULL AND target_preference_id IS NOT NULL)",
            name="ck_suggestion_target",
        ),
        sa.CheckConstraint(
            "action IN ('edit', 'disable')", name="ck_suggestion_action"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object'", name="ck_suggestion_payload"
        ),
        sa.CheckConstraint("origin = 'ai'", name="ck_suggestion_origin"),
        sa.CheckConstraint(
            "review_snapshot IS NULL OR jsonb_typeof(review_snapshot) = 'object'",
            name="ck_suggestion_snapshot",
        ),
        sa.CheckConstraint(
            "state IN ('pending', 'approved', 'rejected', 'stale')",
            name="ck_suggestion_state",
        ),
        sa.CheckConstraint("target_revision >= 1", name="ck_suggestion_revision"),
        sa.ForeignKeyConstraint(
            ["target_default_id"], ["merchant_default.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["target_match_id"], ["merchant_match.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["target_merchant_id"], ["merchant.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["target_preference_id"],
            ["classification_preference.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "occurrence_evidence_revision",
        sa.Column("occurrence_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "revision", sa.BigInteger(), server_default=sa.text("1"), nullable=False
        ),
        sa.CheckConstraint("revision >= 1", name="ck_evidence_revision_positive"),
        sa.ForeignKeyConstraint(
            ["occurrence_id"], ["transaction_occurrence.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("occurrence_id"),
    )
    op.create_table(
        "rule_evaluation_work",
        sa.Column("occurrence_id", sa.BigInteger(), nullable=False),
        sa.Column("import_correlation_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(length=9), nullable=False),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.CheckConstraint(
            "(state IN ('pending', 'completed') AND last_error_code IS NULL) OR (state = 'failed' AND last_error_code IS NOT NULL)",
            name="ck_evaluation_work_state",
        ),
        sa.CheckConstraint(
            "last_error_code IS NULL OR last_error_code ~ '^[a-z][a-z0-9_]{0,63}$'",
            name="ck_evaluation_work_error_code",
        ),
        sa.ForeignKeyConstraint(
            ["occurrence_id"], ["transaction_occurrence.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("occurrence_id"),
    )
    op.create_index(
        "ix_evaluation_work_correlation",
        "rule_evaluation_work",
        ["import_correlation_id"],
        unique=False,
    )
    op.create_table(
        "transaction_override",
        sa.Column("occurrence_id", sa.BigInteger(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column(
            "revision", sa.BigInteger(), server_default=sa.text("1"), nullable=False
        ),
        sa.CheckConstraint(
            "category ~ U&'[^\\0009-\\000D\\001C-\\0020\\0085\\00A0\\1680\\2000-\\200A\\2028\\2029\\202F\\205F\\3000]'",
            name="ck_override_category",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_override_revision"),
        sa.ForeignKeyConstraint(
            ["occurrence_id"], ["transaction_occurrence.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("occurrence_id"),
    )
    op.create_table(
        "application_approval",
        sa.Column("conflict_id", sa.BigInteger(), nullable=False),
        sa.Column("ai_revision", sa.BigInteger(), nullable=False),
        sa.Column("confirmed_revision", sa.BigInteger(), nullable=False),
        sa.Column("evidence_revision", sa.BigInteger(), nullable=False),
        sa.Column("merchant_revisions", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint(
            "ai_revision >= 1 AND confirmed_revision >= 1 AND evidence_revision >= 1",
            name="ck_approval_revisions",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(merchant_revisions) = 'array'",
            name="ck_approval_merchant_revisions",
        ),
        sa.ForeignKeyConstraint(
            ["conflict_id"], ["application_conflict.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("conflict_id"),
    )
    op.create_table(
        "rule_evaluation_outcome",
        sa.Column("occurrence_id", sa.BigInteger(), nullable=False),
        sa.Column("evidence_revision", sa.BigInteger(), nullable=False),
        sa.Column("merchant_status", sa.String(length=8), nullable=False),
        sa.Column("merchant_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "matching_candidates",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "category_decision", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "winning_references",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "blocked_ai_conflicts",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(merchant_status = 'resolved' AND merchant_id IS NOT NULL) OR (merchant_status IN ('no_match', 'conflict') AND merchant_id IS NULL)",
            name="ck_outcome_merchant",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(matching_candidates) = 'array' AND jsonb_typeof(category_decision) = 'object' AND jsonb_typeof(winning_references) = 'array' AND jsonb_typeof(blocked_ai_conflicts) = 'array'",
            name="ck_outcome_json_shapes",
        ),
        sa.CheckConstraint(
            "evidence_revision >= 1", name="ck_outcome_evidence_revision"
        ),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["occurrence_id"],
            ["rule_evaluation_work.occurrence_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("occurrence_id"),
    )
    op.execute("INSERT INTO rules_configuration (id) VALUES (1)")


def downgrade() -> None:
    tables = (
        "application_approval",
        "application_conflict",
        "change_suggestion",
        "classification_preference",
        "merchant",
        "merchant_default",
        "merchant_match",
        "occurrence_evidence_revision",
        "rule_evaluation_outcome",
        "rule_evaluation_work",
        "transaction_override",
    )
    bind = op.get_bind()
    bind.execute(sa.text(f"LOCK TABLE {', '.join(tables)} IN ACCESS EXCLUSIVE MODE"))
    populated = bind.execute(
        sa.text(
            "SELECT "
            + " OR ".join(f"EXISTS (SELECT 1 FROM {table})" for table in tables)
        )
    ).scalar_one()
    if populated:
        raise RuntimeError("Cannot downgrade while merchant rules data exists")
    op.drop_table("rule_evaluation_outcome")
    op.drop_table("application_approval")
    op.drop_table("transaction_override")
    op.drop_index("ix_evaluation_work_correlation", table_name="rule_evaluation_work")
    op.drop_table("rule_evaluation_work")
    op.drop_table("occurrence_evidence_revision")
    op.drop_table("change_suggestion")
    op.drop_table("application_conflict")
    op.drop_table("merchant_match")
    op.drop_table("merchant_default")
    op.drop_table("classification_preference")
    op.drop_table("rules_configuration")
    op.drop_table("merchant")
