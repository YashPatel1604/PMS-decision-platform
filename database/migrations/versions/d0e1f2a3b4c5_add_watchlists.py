"""Add watchlists and watchlist_members tables.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-08-10 13:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, Sequence[str], None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "watchlists",
        sa.Column("watchlist_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("watchlist_id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "watchlist_members",
        sa.Column("member_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("watchlist_id", sa.Integer(), nullable=False),
        sa.Column("security_id", sa.String(length=16), nullable=True),
        sa.Column("display_name", sa.String(length=256), nullable=False),
        sa.Column("nse_symbol", sa.String(length=32), nullable=True),
        sa.Column("bse_code", sa.String(length=16), nullable=True),
        sa.Column("isin", sa.String(length=16), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "resolution_status",
            sa.String(length=16),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["security_id"],
            ["securities.security_id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["watchlist_id"],
            ["watchlists.watchlist_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("member_id"),
        sa.UniqueConstraint(
            "watchlist_id",
            "security_id",
            name="uq_watchlist_member_security",
        ),
    )
    op.create_index(
        "ix_watchlist_members_watchlist_id",
        "watchlist_members",
        ["watchlist_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_watchlist_members_watchlist_id", table_name="watchlist_members")
    op.drop_table("watchlist_members")
    op.drop_table("watchlists")
