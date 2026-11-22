"""Represent ambiguous occurrences without inventing a booking status.

Revision ID: 0002_unknown_status
Revises: 0001_ingestion_schema
"""

import sqlalchemy as sa

from alembic import op

revision = "0002_unknown_status"
down_revision = "0001_ingestion_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "transaction_occurrence",
        "booking_status",
        existing_type=sa.String(7),
        nullable=True,
    )
    op.execute(
        "DELETE FROM occurrence_observation WHERE occurrence_id IN "
        "(SELECT id FROM transaction_occurrence WHERE reconciliation_state = 'unresolved')"
    )
    op.execute(
        "UPDATE transaction_occurrence SET booking_status = NULL "
        "WHERE reconciliation_state = 'unresolved'"
    )
    op.create_check_constraint(
        "ck_unknown_status_unresolved",
        "transaction_occurrence",
        "booking_status IS NOT NULL OR reconciliation_state = 'unresolved'",
    )


def downgrade() -> None:
    count = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT count(*) FROM transaction_occurrence WHERE booking_status IS NULL"
            )
        )
        .scalar_one()
    )
    if count:
        raise RuntimeError(
            "Cannot downgrade while occurrences have unknown booking status"
        )
    op.drop_constraint(
        "ck_unknown_status_unresolved", "transaction_occurrence", type_="check"
    )
    op.alter_column(
        "transaction_occurrence",
        "booking_status",
        existing_type=sa.String(7),
        nullable=False,
    )
