"""Align category whitespace validation across storage and the application.

Revision ID: 0006_category_whitespace
Revises: 0005_transaction_enrichment
"""

import sqlalchemy as sa

from alembic import op

revision = "0006_category_whitespace"
down_revision = "0005_transaction_enrichment"
branch_labels = None
depends_on = None

_CATEGORY = r"value ~ U&'[^\0009-\000D\001C-\0020\0085\00A0\1680\2000-\200A\2028\2029\202F\205F\3000]'"
_PREFIX = (
    "(dimension = 'transaction_type' AND value IN ('expense', 'income', 'transfer', 'refund')) OR "
    "(dimension = 'budget_treatment' AND value IN ('ordinary', 'extraordinary', 'excluded')) OR "
)


def upgrade() -> None:
    invalid = (
        op.get_bind()
        .execute(
            sa.text(
                f"SELECT EXISTS (SELECT 1 FROM transaction_classification WHERE dimension = 'category' AND NOT ({_CATEGORY}))"
            )
        )
        .scalar_one()
    )
    if invalid:
        raise RuntimeError("Cannot upgrade while whitespace-only categories exist")
    op.drop_constraint(
        "ck_classification_value", "transaction_classification", type_="check"
    )
    op.create_check_constraint(
        "ck_classification_value",
        "transaction_classification",
        _PREFIX + f"(dimension = 'category' AND {_CATEGORY})",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_classification_value", "transaction_classification", type_="check"
    )
    op.create_check_constraint(
        "ck_classification_value",
        "transaction_classification",
        _PREFIX + "(dimension = 'category' AND value ~ '[^[:space:]]')",
    )
