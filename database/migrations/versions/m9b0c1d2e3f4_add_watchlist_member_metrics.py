"""Add materialized watchlist_member_metrics for instant screener reads.

Revision ID: m9b0c1d2e3f4
Revises: l8a9b0c1d2e3
Create Date: 2026-08-12 14:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "m9b0c1d2e3f4"
down_revision: Union[str, Sequence[str], None] = "l8a9b0c1d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "watchlist_member_metrics",
        sa.Column("member_id", sa.Integer(), sa.ForeignKey("watchlist_members.member_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("watchlist_id", sa.Integer(), sa.ForeignKey("watchlists.watchlist_id", ondelete="CASCADE"), nullable=False),
        sa.Column("computation_version", sa.String(16), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("fiscal_quarter", sa.String(8), nullable=True),
        sa.Column("period_end_date", sa.Date(), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("has_fundamentals", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("fundamentals_stale", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("metrics", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_watchlist_member_metrics_watchlist_id",
        "watchlist_member_metrics",
        ["watchlist_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_watchlist_member_metrics_watchlist_id", table_name="watchlist_member_metrics")
    op.drop_table("watchlist_member_metrics")
