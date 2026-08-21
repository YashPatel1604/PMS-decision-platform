"""Pivot Vol Exp snapshotted per bhav as-of date (Last20 rolling).

Revision ID: r4a5b6c7d8e9
Revises: q3f4a5b6c7d8
Create Date: 2026-08-21 19:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "r4a5b6c7d8e9"
down_revision: Union[str, Sequence[str], None] = "q3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("pivot_vol_exp")
    op.create_table(
        "pivot_vol_exp",
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("vol_exp", sa.Numeric(24, 4), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="last20"),
        sa.PrimaryKeyConstraint("as_of_date", "symbol"),
    )


def downgrade() -> None:
    op.drop_table("pivot_vol_exp")
    op.create_table(
        "pivot_vol_exp",
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("vol_exp", sa.Numeric(24, 4), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="bars"),
        sa.PrimaryKeyConstraint("symbol"),
    )
