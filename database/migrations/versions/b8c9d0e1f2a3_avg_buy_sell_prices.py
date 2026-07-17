"""Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-07-17 17:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "episode_performance",
        sa.Column("average_buy_price", sa.Numeric(precision=18, scale=4), nullable=True),
    )
    op.add_column(
        "episode_performance",
        sa.Column("average_sell_price", sa.Numeric(precision=18, scale=4), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("episode_performance", "average_sell_price")
    op.drop_column("episode_performance", "average_buy_price")
