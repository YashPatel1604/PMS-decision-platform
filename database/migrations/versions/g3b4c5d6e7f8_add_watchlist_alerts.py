"""Add watchlist_alerts table for SAST / insider notifications.

Revision ID: g3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-08-10 14:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "g3b4c5d6e7f8"
down_revision: Union[str, Sequence[str], None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "watchlist_alerts",
        sa.Column("alert_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("watchlist_id", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=True),
        sa.Column("dedupe_key", sa.String(length=512), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("disclosure_date", sa.Date(), nullable=False),
        sa.Column("bse_code", sa.String(length=16), nullable=False),
        sa.Column("company_name", sa.String(length=256), nullable=False),
        sa.Column("person_name", sa.String(length=256), nullable=False),
        sa.Column("category", sa.String(length=128), nullable=False),
        sa.Column("transaction_type", sa.String(length=128), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 2), nullable=True),
        sa.Column("value", sa.Numeric(20, 2), nullable=True),
        sa.Column("pct_pre", sa.Numeric(10, 4), nullable=True),
        sa.Column("pct_post", sa.Numeric(10, 4), nullable=True),
        sa.Column("mode", sa.String(length=128), nullable=False),
        sa.Column("regulation", sa.String(length=64), nullable=False),
        sa.Column("market_cap_cr", sa.Numeric(20, 2), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["watchlist_members.member_id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["watchlist_id"],
            ["watchlists.watchlist_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("alert_id"),
        sa.UniqueConstraint(
            "watchlist_id",
            "dedupe_key",
            name="uq_watchlist_alert_dedupe",
        ),
    )
    op.create_index(
        "ix_watchlist_alerts_watchlist_id",
        "watchlist_alerts",
        ["watchlist_id"],
    )
    op.create_index(
        "ix_watchlist_alerts_unacknowledged",
        "watchlist_alerts",
        ["watchlist_id", "acknowledged"],
    )


def downgrade() -> None:
    op.drop_index("ix_watchlist_alerts_unacknowledged", table_name="watchlist_alerts")
    op.drop_index("ix_watchlist_alerts_watchlist_id", table_name="watchlist_alerts")
    op.drop_table("watchlist_alerts")
