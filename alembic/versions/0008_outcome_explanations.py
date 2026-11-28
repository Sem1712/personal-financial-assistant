"""Preserve complete merchant and category conflict decisions.

Revision ID: 0008_outcome_explanations
Revises: 0007_merchant_rules
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0008_outcome_explanations"
down_revision = "0007_merchant_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rule_evaluation_outcome",
        sa.Column("merchant_decision", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "rule_evaluation_outcome",
        sa.Column("category_conflict_candidates", postgresql.JSONB(), nullable=True),
    )
    op.create_check_constraint(
        "ck_outcome_explanation_shapes",
        "rule_evaluation_outcome",
        "(merchant_decision IS NULL OR jsonb_typeof(merchant_decision) = 'object') "
        "AND (category_conflict_candidates IS NULL OR "
        "jsonb_typeof(category_conflict_candidates) = 'array')",
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM rule_evaluation_outcome "
            "WHERE merchant_decision IS NOT NULL OR category_conflict_candidates IS NOT NULL)"
        )
    ):
        raise RuntimeError("Cannot downgrade: evaluation explanations would be lost.")
    op.drop_constraint(
        "ck_outcome_explanation_shapes", "rule_evaluation_outcome", type_="check"
    )
    op.drop_column("rule_evaluation_outcome", "category_conflict_candidates")
    op.drop_column("rule_evaluation_outcome", "merchant_decision")
