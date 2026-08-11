"""Watchlist refresh lock table.

Revision ID: h4c5d6e7f8a9
Revises: g3b4c5d6e7f8
Create Date: 2026-08-10 15:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "h4c5d6e7f8a9"
down_revision: Union[str, Sequence[str], None] = "g3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "watchlist_refresh_locks",
        sa.Column("watchlist_id", sa.Integer(), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["watchlist_id"],
            ["watchlists.watchlist_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("watchlist_id"),
    )


def downgrade() -> None:
    op.drop_table("watchlist_refresh_locks")
