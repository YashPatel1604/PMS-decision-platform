"""Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-17 16:20:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "episode_performance",
        sa.Column("peak_price_during_hold", sa.Numeric(precision=18, scale=4), nullable=True),
    )
    op.add_column("episode_performance", sa.Column("peak_price_date", sa.Date(), nullable=True))
    op.add_column(
        "episode_performance",
        sa.Column("exit_adjusted_close", sa.Numeric(precision=18, scale=4), nullable=True),
    )
    op.add_column(
        "episode_performance",
        sa.Column("missed_upside_vs_peak_pct", sa.Numeric(precision=18, scale=6), nullable=True),
    )
    op.add_column(
        "episode_performance",
        sa.Column("stock_annualized_return_pct", sa.Numeric(precision=18, scale=6), nullable=True),
    )
    op.add_column("episode_performance", sa.Column("ownership_trading_days", sa.Integer(), nullable=True))
    op.add_column("sell_assessments", sa.Column("assessment_flags", sa.String(length=256), nullable=True))
    op.alter_column(
        "sell_assessments",
        "exit_assessment",
        existing_type=sa.String(length=32),
        type_=sa.String(length=64),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "sell_assessments",
        "exit_assessment",
        existing_type=sa.String(length=64),
        type_=sa.String(length=32),
        existing_nullable=False,
    )
    op.drop_column("sell_assessments", "assessment_flags")
    op.drop_column("episode_performance", "ownership_trading_days")
    op.drop_column("episode_performance", "stock_annualized_return_pct")
    op.drop_column("episode_performance", "missed_upside_vs_peak_pct")
    op.drop_column("episode_performance", "exit_adjusted_close")
    op.drop_column("episode_performance", "peak_price_date")
    op.drop_column("episode_performance", "peak_price_during_hold")
