"""Explicit holding units, quote provenance and revocable persistent sessions."""

from alembic import op
import sqlalchemy as sa

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "positions", sa.Column("quote_stale", sa.Boolean(), nullable=False, server_default="0")
    )
    op.add_column("positions", sa.Column("tracking_mode", sa.String(16), nullable=True))
    op.add_column("positions", sa.Column("external_id", sa.String(180), nullable=True))
    op.add_column("positions", sa.Column("quote_as_of", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        "UPDATE positions SET tracking_mode = CASE WHEN asset_type IN "
        "('rendafixa', 'rendafixa_internacional') AND current_price IS NULL "
        "THEN 'balance' ELSE 'units' END"
    )
    op.add_column(
        "aporte_allocations", sa.Column("tracking_mode_snapshot", sa.String(16), nullable=True)
    )
    op.execute(
        "UPDATE aporte_allocations SET tracking_mode_snapshot = CASE WHEN asset_type_snapshot IN "
        "('rendafixa', 'rendafixa_internacional') AND price_at_aporte_brl IS NULL "
        "THEN 'balance' ELSE 'units' END"
    )
    op.create_table(
        "auth_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])


def downgrade():
    op.drop_table("auth_sessions")
    op.drop_column("aporte_allocations", "tracking_mode_snapshot")
    op.drop_column("positions", "quote_as_of")
    op.drop_column("positions", "quote_stale")
    op.drop_column("positions", "external_id")
    op.drop_column("positions", "tracking_mode")
