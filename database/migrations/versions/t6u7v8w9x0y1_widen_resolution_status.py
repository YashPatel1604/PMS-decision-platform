"""Widen watchlist resolution_status for EXCHANGE_RESOLVED.

Revision ID: t6u7v8w9x0y1
Revises: s5t6u7v8w9x0
Create Date: 2026-08-22 14:45:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "t6u7v8w9x0y1"
down_revision: Union[str, Sequence[str], None] = "s5t6u7v8w9x0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "watchlist_members",
        "resolution_status",
        existing_type=sa.String(length=16),
        type_=sa.String(length=32),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "watchlist_members",
        "resolution_status",
        existing_type=sa.String(length=32),
        type_=sa.String(length=16),
        existing_nullable=False,
    )
