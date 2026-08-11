"""Add promoter_snapshots table.

Revision ID: j6e7f8a9b0c1
Revises: i5d6e7f8a9b0
Create Date: 2026-08-11 09:10:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "j6e7f8a9b0c1"
down_revision: Union[str, Sequence[str], None] = "i5d6e7f8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "promoter_snapshots",
        sa.Column("promoter_snapshot_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("identifier_type", sa.String(length=32), nullable=False),
        sa.Column("identifier", sa.String(length=64), nullable=False),
        sa.Column("security_id", sa.String(length=16), nullable=True),
        sa.Column("quarter_end_date", sa.Date(), nullable=False),
        sa.Column("promoter_holding_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("promoter_holding_change_pp", sa.Numeric(10, 4), nullable=True),
        sa.Column("pledged_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["security_id"],
            ["securities.security_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("promoter_snapshot_id"),
        sa.UniqueConstraint(
            "identifier_type",
            "identifier",
            "quarter_end_date",
            name="uq_promoter_snapshot_identity",
        ),
    )
    op.create_index(
        "ix_promoter_snapshots_identifier",
        "promoter_snapshots",
        ["identifier_type", "identifier"],
    )


def downgrade() -> None:
    op.drop_index("ix_promoter_snapshots_identifier", table_name="promoter_snapshots")
    op.drop_table("promoter_snapshots")
