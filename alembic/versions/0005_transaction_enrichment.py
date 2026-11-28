"""Add independent occurrence classification and context.

Revision ID: 0005_transaction_enrichment
Revises: 0004_ui_import_run
"""

import sqlalchemy as sa

from alembic import op

revision = "0005_transaction_enrichment"
down_revision = "0004_ui_import_run"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transaction_classification",
        sa.Column("occurrence_id", sa.BigInteger(), nullable=False),
        sa.Column("dimension", sa.String(16), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("status", sa.String(11), nullable=False),
        sa.Column("source", sa.String(4), nullable=False),
        sa.Column("confidence", sa.Numeric()),
        sa.PrimaryKeyConstraint("occurrence_id", "dimension"),
        sa.ForeignKeyConstraint(
            ["occurrence_id"], ["transaction_occurrence.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "dimension IN ('transaction_type', 'category', 'budget_treatment')",
            name="ck_classification_dimension",
        ),
        sa.CheckConstraint(
            "(dimension = 'transaction_type' AND value IN ('expense', 'income', 'transfer', 'refund')) OR "
            "(dimension = 'budget_treatment' AND value IN ('ordinary', 'extraordinary', 'excluded')) OR "
            "(dimension = 'category' AND value ~ '[^[:space:]]')",
            name="ck_classification_value",
        ),
        sa.CheckConstraint(
            "status IN ('provisional', 'confirmed')", name="ck_classification_status"
        ),
        sa.CheckConstraint(
            "source IN ('ai', 'rule', 'user')", name="ck_classification_source"
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 100 "
            "AND scale(confidence) <= 2)",
            name="ck_classification_confidence",
        ),
    )
    op.create_table(
        "transaction_context",
        sa.Column("occurrence_id", sa.BigInteger(), nullable=False, primary_key=True),
        sa.Column("user_annotation", sa.Text()),
        sa.Column("user_explanation", sa.Text()),
        sa.Column("ai_explanation", sa.Text()),
        sa.ForeignKeyConstraint(
            ["occurrence_id"], ["transaction_occurrence.id"], ondelete="RESTRICT"
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    populated = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM transaction_classification) OR "
            "EXISTS (SELECT 1 FROM transaction_context WHERE user_annotation IS NOT NULL "
            "OR user_explanation IS NOT NULL OR ai_explanation IS NOT NULL)"
        )
    ).scalar_one()
    if populated:
        raise RuntimeError("Cannot downgrade while transaction enrichment exists")
    op.drop_table("transaction_context")
    op.drop_table("transaction_classification")
