"""Add watchlist resolution metadata and audit log.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-08-10 14:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "d0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "watchlist_members",
        sa.Column("resolution_source", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "watchlist_members",
        sa.Column("resolution_note", sa.Text(), nullable=True),
    )
    op.add_column(
        "watchlist_members",
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "watchlist_resolution_logs",
        sa.Column("log_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("watchlist_id", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=True),
        sa.Column(
            "attempted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("source_attempted", sa.String(length=16), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["watchlist_members.member_id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["watchlist_id"],
            ["watchlists.watchlist_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("log_id"),
    )
    op.create_index(
        "ix_watchlist_resolution_logs_watchlist_id",
        "watchlist_resolution_logs",
        ["watchlist_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_watchlist_resolution_logs_watchlist_id",
        table_name="watchlist_resolution_logs",
    )
    op.drop_table("watchlist_resolution_logs")
    op.drop_column("watchlist_members", "resolved_at")
    op.drop_column("watchlist_members", "resolution_note")
    op.drop_column("watchlist_members", "resolution_source")
