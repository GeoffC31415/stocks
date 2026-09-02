"""market price cache

Adds the durable market-history cache (``market_price_points``) and the FX
rate cache (``market_fx_points``) introduced by the market-data foundation.

Revision ID: 3c9d5a1e7b02
Revises: f7e6d85d8a52
Create Date: 2026-09-02 22:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3c9d5a1e7b02"
down_revision: str | Sequence[str] | None = "f7e6d85d8a52"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "market_price_points",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("adjusted_close", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "symbol", "date", name="uq_market_price_point"),
    )
    with op.batch_alter_table("market_price_points", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_market_price_points_source"), ["source"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_market_price_points_symbol"), ["symbol"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_market_price_points_date"), ["date"], unique=False)

    op.create_table(
        "market_fx_points",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("pair", sa.String(length=16), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("rate", sa.Float(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "pair", "date", name="uq_market_fx_point"),
    )
    with op.batch_alter_table("market_fx_points", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_market_fx_points_source"), ["source"], unique=False)
        batch_op.create_index(batch_op.f("ix_market_fx_points_pair"), ["pair"], unique=False)
        batch_op.create_index(batch_op.f("ix_market_fx_points_date"), ["date"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("market_fx_points", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_market_fx_points_date"))
        batch_op.drop_index(batch_op.f("ix_market_fx_points_pair"))
        batch_op.drop_index(batch_op.f("ix_market_fx_points_source"))
    op.drop_table("market_fx_points")
    with op.batch_alter_table("market_price_points", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_market_price_points_date"))
        batch_op.drop_index(batch_op.f("ix_market_price_points_symbol"))
        batch_op.drop_index(batch_op.f("ix_market_price_points_source"))
    op.drop_table("market_price_points")
