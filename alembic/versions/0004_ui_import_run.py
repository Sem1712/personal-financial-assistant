"""Add durable UI import status without storing financial data.

Revision ID: 0004_ui_import_run
Revises: 0003_empty_source
"""

import sqlalchemy as sa

from alembic import op

revision = "0004_ui_import_run"
down_revision = "0003_empty_source"
branch_labels = None
depends_on = None

COUNT_COLUMNS = (
    "files_seen",
    "files_processed",
    "files_unchanged",
    "rows_read",
    "transactions_added",
    "transactions_updated",
    "observations_unchanged",
    "unresolved_observations",
)


def upgrade() -> None:
    op.create_table(
        "ui_import_run",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("state", sa.String(10), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        *(sa.Column(name, sa.BigInteger()) for name in COUNT_COLUMNS),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_message", sa.Text()),
        sa.CheckConstraint(
            "state IN ('running', 'succeeded', 'no_files', 'failed', 'unknown')",
            name="ck_ui_import_run_state",
        ),
        sa.CheckConstraint(
            "(state = 'running' AND finished_at IS NULL) OR "
            "(state <> 'running' AND finished_at IS NOT NULL)",
            name="ck_ui_import_run_finished",
        ),
        sa.CheckConstraint(
            "(state = 'failed' AND error_code IS NOT NULL AND error_message IS NOT NULL) "
            "OR (state <> 'failed' AND error_code IS NULL AND error_message IS NULL)",
            name="ck_ui_import_run_error",
        ),
        *(
            sa.CheckConstraint(f"{name} >= 0", name=f"ck_ui_import_run_{name}")
            for name in COUNT_COLUMNS
        ),
        sa.CheckConstraint(
            "(state IN ('succeeded', 'no_files') AND "
            + " AND ".join(f"{name} IS NOT NULL" for name in COUNT_COLUMNS)
            + ") OR (state NOT IN ('succeeded', 'no_files') AND "
            + " AND ".join(f"{name} IS NULL" for name in COUNT_COLUMNS)
            + ")",
            name="ck_ui_import_run_counts",
        ),
    )
    op.create_index("ix_ui_import_run_latest", "ui_import_run", ["started_at", "id"])


def downgrade() -> None:
    op.drop_index("ix_ui_import_run_latest", table_name="ui_import_run")
    op.drop_table("ui_import_run")
