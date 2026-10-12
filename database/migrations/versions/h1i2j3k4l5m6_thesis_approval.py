"""Add human thesis approval without rewriting existing saved versions.

Revision ID: h1i2j3k4l5m6
Revises: g0h1i2j3k4l5
Create Date: 2026-10-12 00:20:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "h1i2j3k4l5m6"
down_revision: Union[str, Sequence[str], None] = "g0h1i2j3k4l5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("investment_theses", sa.Column("approved_by", sa.String(length=128), nullable=True))
    op.add_column(
        "investment_theses",
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "uq_one_approved_thesis",
        "investment_theses",
        ["security_id"],
        unique=True,
        postgresql_where=sa.text("status = 'approved'"),
        sqlite_where=sa.text("status = 'approved'"),
    )


def downgrade() -> None:
    op.drop_index("uq_one_approved_thesis", table_name="investment_theses")
    op.drop_column("investment_theses", "approved_at")
    op.drop_column("investment_theses", "approved_by")
