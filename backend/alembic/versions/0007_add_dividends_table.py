"""add dividends cache table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-06 17:15:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dividends",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("ex_date", sa.Date(), nullable=True),
        sa.Column("amount_per_share", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="BRL"),
        sa.Column(
            "dividend_type", sa.String(length=32), nullable=False, server_default="Dividendo"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ticker",
            "payment_date",
            "amount_per_share",
            name="uq_dividends_ticker_paydate_amount",
        ),
    )
    op.create_index(op.f("ix_dividends_ticker"), "dividends", ["ticker"], unique=False)
    op.create_index(op.f("ix_dividends_payment_date"), "dividends", ["payment_date"], unique=False)
    op.create_index(op.f("ix_dividends_ex_date"), "dividends", ["ex_date"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_dividends_ex_date"), table_name="dividends")
    op.drop_index(op.f("ix_dividends_payment_date"), table_name="dividends")
    op.drop_index(op.f("ix_dividends_ticker"), table_name="dividends")
    op.drop_table("dividends")
