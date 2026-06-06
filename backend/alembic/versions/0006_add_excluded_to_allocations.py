"""add excluded flag to aporte_allocations

Revision ID: a1b2c3d4e5f6
Revises: 9c3b5d72f104
Create Date: 2026-06-06 12:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "9c3b5d72f104"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("aporte_allocations") as batch:
        batch.add_column(
            sa.Column(
                "excluded",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("aporte_allocations") as batch:
        batch.drop_column("excluded")
