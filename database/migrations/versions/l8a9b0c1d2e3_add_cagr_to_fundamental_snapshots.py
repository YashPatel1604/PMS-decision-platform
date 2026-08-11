"""Add 3y/5y CAGR columns to fundamental_snapshots.

Revision ID: l8a9b0c1d2e3
Revises: k7f8a9b0c1d2
Create Date: 2026-08-11 09:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "l8a9b0c1d2e3"
down_revision: Union[str, Sequence[str], None] = "k7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("fundamental_snapshots", sa.Column("sales_3y_cagr", sa.Numeric(10, 4), nullable=True))
    op.add_column("fundamental_snapshots", sa.Column("sales_5y_cagr", sa.Numeric(10, 4), nullable=True))
    op.add_column("fundamental_snapshots", sa.Column("pat_3y_cagr", sa.Numeric(10, 4), nullable=True))
    op.add_column("fundamental_snapshots", sa.Column("pat_5y_cagr", sa.Numeric(10, 4), nullable=True))


def downgrade() -> None:
    op.drop_column("fundamental_snapshots", "pat_5y_cagr")
    op.drop_column("fundamental_snapshots", "pat_3y_cagr")
    op.drop_column("fundamental_snapshots", "sales_5y_cagr")
    op.drop_column("fundamental_snapshots", "sales_3y_cagr")
