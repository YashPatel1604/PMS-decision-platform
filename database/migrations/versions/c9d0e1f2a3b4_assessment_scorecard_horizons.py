"""Add dimensional scorecards and fixed post-exit horizons.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-07-21 15:10:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, Sequence[str], None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "sell_assessments",
        "assessment_flags",
        existing_type=sa.String(length=256),
        type_=sa.String(length=512),
        existing_nullable=True,
    )
    op.add_column(
        "sell_assessments",
        sa.Column("ownership_flags", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "sell_assessments",
        sa.Column("post_exit_flags", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "sell_assessments",
        sa.Column("assessment_confidence", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "sell_assessments",
        sa.Column("assessment_evidence", sa.Text(), nullable=True),
    )

    op.create_table(
        "post_exit_horizon_performance",
        sa.Column(
            "post_exit_horizon_performance_id",
            sa.Integer(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("episode_id", sa.Integer(), nullable=False),
        sa.Column("horizon", sa.String(length=16), nullable=False),
        sa.Column("exit_date", sa.Date(), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("comparison_date", sa.Date(), nullable=True),
        sa.Column("days_after_exit", sa.Integer(), nullable=True),
        sa.Column(
            "security_return_after_exit",
            sa.Numeric(precision=18, scale=6),
            nullable=True,
        ),
        sa.Column(
            "smallcap_return_after_exit",
            sa.Numeric(precision=18, scale=6),
            nullable=True,
        ),
        sa.Column(
            "excess_vs_smallcap_after_exit",
            sa.Numeric(precision=18, scale=6),
            nullable=True,
        ),
        sa.Column(
            "provisional_portfolio_return_after_exit",
            sa.Numeric(precision=18, scale=6),
            nullable=True,
        ),
        sa.Column(
            "provisional_excess_vs_portfolio_after_exit",
            sa.Numeric(precision=18, scale=6),
            nullable=True,
        ),
        sa.Column("calculation_version", sa.String(length=32), nullable=False),
        sa.Column("data_quality_status", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["episode_id"],
            ["investment_episodes.episode_id"],
        ),
        sa.PrimaryKeyConstraint("post_exit_horizon_performance_id"),
        sa.UniqueConstraint(
            "episode_id",
            "horizon",
            name="uq_post_exit_horizon_episode_horizon",
        ),
    )


def downgrade() -> None:
    op.drop_table("post_exit_horizon_performance")
    op.drop_column("sell_assessments", "assessment_evidence")
    op.drop_column("sell_assessments", "assessment_confidence")
    op.drop_column("sell_assessments", "post_exit_flags")
    op.drop_column("sell_assessments", "ownership_flags")
    op.alter_column(
        "sell_assessments",
        "assessment_flags",
        existing_type=sa.String(length=512),
        type_=sa.String(length=256),
        existing_nullable=True,
    )
