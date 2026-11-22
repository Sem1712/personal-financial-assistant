"""Create bank ingestion tables.

Revision ID: 0001_ingestion_schema
Revises:
"""

import sqlalchemy as sa

from alembic import op

revision = "0001_ingestion_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "selected_account",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("account_reference", sa.Text(), nullable=False, unique=True),
        sa.Column("display_label", sa.Text()),
    )
    op.create_table(
        "source_file",
        sa.Column("sha256", sa.String(64), primary_key=True),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("transaction_row_count", sa.Integer(), nullable=False),
        sa.Column(
            "account_id",
            sa.BigInteger(),
            sa.ForeignKey("selected_account.id"),
            nullable=False,
        ),
        sa.CheckConstraint("transaction_row_count >= 0", name="ck_source_row_count"),
    )
    op.create_table(
        "transaction_observation",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "source_file_sha256",
            sa.String(64),
            sa.ForeignKey("source_file.sha256"),
            nullable=False,
        ),
        sa.Column("sheet_index", sa.Integer(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column(
            "account_id",
            sa.BigInteger(),
            sa.ForeignKey("selected_account.id"),
            nullable=False,
        ),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("operation", sa.Text()),
        sa.Column("details", sa.Text()),
        sa.Column("booking_status", sa.String(7), nullable=False),
        sa.Column("category", sa.Text()),
        sa.Column("candidate_key", sa.String(64), nullable=False),
        sa.Column("occurrence_ordinal", sa.Integer(), nullable=False),
        sa.UniqueConstraint("source_file_sha256", "sheet_index", "row_number"),
        sa.CheckConstraint(
            "sheet_index >= 0 AND row_number >= 1", name="ck_source_location"
        ),
        sa.CheckConstraint("occurrence_ordinal >= 1", name="ck_occurrence_ordinal"),
        sa.CheckConstraint("currency = 'EUR'", name="ck_observation_currency"),
        sa.CheckConstraint(
            "booking_status IN ('pending', 'booked')", name="ck_observation_status"
        ),
    )
    op.create_index(
        "ix_transaction_observation_candidate_key",
        "transaction_observation",
        ["candidate_key"],
    )
    op.create_table(
        "transaction_occurrence",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "account_id",
            sa.BigInteger(),
            sa.ForeignKey("selected_account.id"),
            nullable=False,
        ),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("booking_status", sa.String(7), nullable=False),
        sa.Column("reconciliation_state", sa.String(12), nullable=False),
        sa.CheckConstraint("currency = 'EUR'", name="ck_occurrence_currency"),
        sa.CheckConstraint(
            "booking_status IN ('pending', 'booked')", name="ck_occurrence_status"
        ),
        sa.CheckConstraint(
            "reconciliation_state IN ('confirmed', 'unresolved', 'pending-only')",
            name="ck_reconciliation_state",
        ),
    )
    op.create_table(
        "occurrence_observation",
        sa.Column(
            "occurrence_id",
            sa.BigInteger(),
            sa.ForeignKey("transaction_occurrence.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "observation_id",
            sa.BigInteger(),
            sa.ForeignKey("transaction_observation.id"),
            primary_key=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("occurrence_observation")
    op.drop_table("transaction_occurrence")
    op.drop_index(
        "ix_transaction_observation_candidate_key", table_name="transaction_observation"
    )
    op.drop_table("transaction_observation")
    op.drop_table("source_file")
    op.drop_table("selected_account")
