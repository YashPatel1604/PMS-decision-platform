"""Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-17 15:35:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "episode_cash_flows",
        sa.Column("episode_cash_flow_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("episode_id", sa.Integer(), nullable=False),
        sa.Column("flow_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("flow_type", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("source_reference", sa.String(length=64), nullable=True),
        sa.Column("calculation_version", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["episode_id"], ["investment_episodes.episode_id"]),
        sa.PrimaryKeyConstraint("episode_cash_flow_id"),
    )
    op.create_table(
        "episode_performance",
        sa.Column("episode_performance_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("episode_id", sa.Integer(), nullable=False),
        sa.Column("security_id", sa.String(length=16), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("exit_date", sa.Date(), nullable=False),
        sa.Column("holding_days", sa.Integer(), nullable=False),
        sa.Column("total_invested", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("total_sale_proceeds", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("dividends_received", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("total_profit_loss", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("total_return_pct", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("stock_xirr", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("smallcap_return_pct", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("smallcap_annualized_return", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("excess_vs_smallcap", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("benchmark_code", sa.String(length=64), nullable=True),
        sa.Column("benchmark_start_level", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("benchmark_end_level", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("calculation_version", sa.String(length=32), nullable=False),
        sa.Column("data_quality_status", sa.String(length=32), nullable=False),
        sa.Column("data_quality_notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["episode_id"], ["investment_episodes.episode_id"]),
        sa.ForeignKeyConstraint(["security_id"], ["securities.security_id"]),
        sa.PrimaryKeyConstraint("episode_performance_id"),
        sa.UniqueConstraint("episode_id", name="uq_episode_performance_episode_id"),
    )


def downgrade() -> None:
    op.drop_table("episode_performance")
    op.drop_table("episode_cash_flows")
