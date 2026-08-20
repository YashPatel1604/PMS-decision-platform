"""Store Excel AllSymbols Vol Exp for exact Daily sheet match.

Revision ID: q3f4a5b6c7d8
Revises: p2e3f4a5b6c7
Create Date: 2026-08-20 20:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "q3f4a5b6c7d8"
down_revision: Union[str, Sequence[str], None] = "p2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pivot_vol_exp",
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("vol_exp", sa.Numeric(24, 4), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="bars"),
        sa.PrimaryKeyConstraint("symbol"),
    )


def downgrade() -> None:
    op.drop_table("pivot_vol_exp")
