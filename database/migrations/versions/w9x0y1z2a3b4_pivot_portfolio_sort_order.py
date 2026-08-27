"""Add sort_order to pivot_portfolio_symbols (selection order).

Revision ID: w9x0y1z2a3b4
Revises: v8w9x0y1z2a3
Create Date: 2026-08-27 15:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "w9x0y1z2a3b4"
down_revision: Union[str, Sequence[str], None] = "v8w9x0y1z2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pivot_portfolio_symbols",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    # Backfill existing rows with a stable order (alpha); new adds use max+1.
    op.execute(
        """
        UPDATE pivot_portfolio_symbols AS p
        SET sort_order = sub.rn
        FROM (
            SELECT symbol, ROW_NUMBER() OVER (ORDER BY symbol) AS rn
            FROM pivot_portfolio_symbols
        ) AS sub
        WHERE p.symbol = sub.symbol
        """
    )
    op.alter_column("pivot_portfolio_symbols", "sort_order", server_default=None)


def downgrade() -> None:
    op.drop_column("pivot_portfolio_symbols", "sort_order")
