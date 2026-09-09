"""Add verified external cash events and successful full-history coverage.

Revision ID: 7e4b8c2a901d
Revises: 3c9d5a1e7b02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7e4b8c2a901d"
down_revision: str | Sequence[str] | None = "3c9d5a1e7b02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "external_cash_flows",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("account_name", sa.String(512), nullable=False),
        sa.Column("reference", sa.String(512), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("amount_gbp", sa.Float(), nullable=False),
        sa.UniqueConstraint("source", "account_name", "reference", name="uq_external_cash_flow"),
    )
    op.create_index("ix_external_cash_flows_account_name", "external_cash_flows", ["account_name"])
    op.create_index("ix_external_cash_flows_occurred_at", "external_cash_flows", ["occurred_at"])
    op.create_table(
        "cash_flow_coverage",
        sa.Column("account_name", sa.String(512), primary_key=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("cash_flow_coverage")
    op.drop_table("external_cash_flows")
