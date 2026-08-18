"""Cache BSE insider filings per calendar day.

Revision ID: o1d2e3f4a5b6
Revises: n0c1d2e3f4a5
Create Date: 2026-08-18 13:20:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "o1d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "n0c1d2e3f4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "insider_disclosure_days",
        sa.Column("disclosure_date", sa.Date(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("truncated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("rows", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("disclosure_date"),
    )


def downgrade() -> None:
    op.drop_table("insider_disclosure_days")
