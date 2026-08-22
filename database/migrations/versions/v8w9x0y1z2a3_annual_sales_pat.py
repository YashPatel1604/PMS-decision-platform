"""Add sales and PAT to annual_fundamentals_snapshots for FY CAGR endpoints.

Revision ID: v8w9x0y1z2a3
Revises: u7v8w9x0y1z2
Create Date: 2026-08-22 17:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v8w9x0y1z2a3"
down_revision: Union[str, Sequence[str], None] = "u7v8w9x0y1z2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "annual_fundamentals_snapshots",
        sa.Column("sales", sa.Numeric(20, 2), nullable=True),
    )
    op.add_column(
        "annual_fundamentals_snapshots",
        sa.Column("pat", sa.Numeric(20, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("annual_fundamentals_snapshots", "pat")
    op.drop_column("annual_fundamentals_snapshots", "sales")
