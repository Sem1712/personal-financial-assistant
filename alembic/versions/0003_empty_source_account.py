"""Allow accountless source files only for empty exports.

Revision ID: 0003_empty_source
Revises: 0002_unknown_status
"""

import sqlalchemy as sa

from alembic import op

revision = "0003_empty_source"
down_revision = "0002_unknown_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "source_file", "account_id", existing_type=sa.BigInteger(), nullable=True
    )
    op.create_check_constraint(
        "ck_source_account_or_empty",
        "source_file",
        "account_id IS NOT NULL OR transaction_row_count = 0",
    )


def downgrade() -> None:
    count = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM source_file WHERE account_id IS NULL"))
        .scalar_one()
    )
    if count:
        raise RuntimeError("Cannot downgrade while empty sources have no account")
    op.drop_constraint("ck_source_account_or_empty", "source_file", type_="check")
    op.alter_column(
        "source_file", "account_id", existing_type=sa.BigInteger(), nullable=False
    )
