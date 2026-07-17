"""Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-17 15:45:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "episode_performance",
        sa.Column("portfolio_return_pct", sa.Numeric(precision=18, scale=6), nullable=True),
    )
    op.add_column(
        "episode_performance",
        sa.Column("portfolio_annualized_return", sa.Numeric(precision=18, scale=6), nullable=True),
    )
    op.add_column(
        "episode_performance",
        sa.Column("excess_vs_portfolio", sa.Numeric(precision=18, scale=6), nullable=True),
    )
    op.add_column(
        "episode_performance",
        sa.Column("max_drawdown", sa.Numeric(precision=18, scale=6), nullable=True),
    )
    op.add_column(
        "episode_performance",
        sa.Column("max_unrealized_gain", sa.Numeric(precision=18, scale=6), nullable=True),
    )
    op.add_column("episode_performance", sa.Column("days_below_cost", sa.Integer(), nullable=True))
    op.add_column(
        "episode_performance",
        sa.Column("days_underperforming_benchmark", sa.Integer(), nullable=True),
    )

    op.create_table(
        "post_exit_performance",
        sa.Column("post_exit_performance_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("episode_id", sa.Integer(), nullable=False),
        sa.Column("exit_date", sa.Date(), nullable=False),
        sa.Column("comparison_date", sa.Date(), nullable=True),
        sa.Column("security_return_after_exit", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("portfolio_return_after_exit", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("smallcap_return_after_exit", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column(
            "excess_vs_portfolio_after_exit",
            sa.Numeric(precision=18, scale=6),
            nullable=True,
        ),
        sa.Column(
            "excess_vs_smallcap_after_exit",
            sa.Numeric(precision=18, scale=6),
            nullable=True,
        ),
        sa.Column("maximum_gain_after_exit", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("maximum_loss_after_exit", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("calculation_version", sa.String(length=32), nullable=False),
        sa.Column("data_quality_status", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["episode_id"], ["investment_episodes.episode_id"]),
        sa.PrimaryKeyConstraint("post_exit_performance_id"),
        sa.UniqueConstraint("episode_id", name="uq_post_exit_performance_episode_id"),
    )
    op.create_table(
        "sell_assessments",
        sa.Column("sell_assessment_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("episode_id", sa.Integer(), nullable=False),
        sa.Column("exit_assessment", sa.String(length=32), nullable=False),
        sa.Column("assessment_reason", sa.Text(), nullable=False),
        sa.Column("calculation_version", sa.String(length=32), nullable=False),
        sa.Column("data_quality_status", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["episode_id"], ["investment_episodes.episode_id"]),
        sa.PrimaryKeyConstraint("sell_assessment_id"),
        sa.UniqueConstraint("episode_id", name="uq_sell_assessments_episode_id"),
    )


def downgrade() -> None:
    op.drop_table("sell_assessments")
    op.drop_table("post_exit_performance")
    op.drop_column("episode_performance", "days_underperforming_benchmark")
    op.drop_column("episode_performance", "days_below_cost")
    op.drop_column("episode_performance", "max_unrealized_gain")
    op.drop_column("episode_performance", "max_drawdown")
    op.drop_column("episode_performance", "excess_vs_portfolio")
    op.drop_column("episode_performance", "portfolio_annualized_return")
    op.drop_column("episode_performance", "portfolio_return_pct")
