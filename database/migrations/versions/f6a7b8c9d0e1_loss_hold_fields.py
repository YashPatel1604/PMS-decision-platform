"""Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-17 16:50:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("episode_performance", sa.Column("first_below_cost_date", sa.Date(), nullable=True))
    op.add_column(
        "episode_performance",
        sa.Column("days_held_after_first_loss", sa.Integer(), nullable=True),
    )
    op.add_column(
        "episode_performance",
        sa.Column("calendar_days_held_after_first_loss", sa.Integer(), nullable=True),
    )
    op.add_column(
        "episode_performance",
        sa.Column("was_profitable_before_loss", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("episode_performance", "was_profitable_before_loss")
    op.drop_column("episode_performance", "calendar_days_held_after_first_loss")
    op.drop_column("episode_performance", "days_held_after_first_loss")
    op.drop_column("episode_performance", "first_below_cost_date")
