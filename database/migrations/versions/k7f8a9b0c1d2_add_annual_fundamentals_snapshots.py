"""Add annual_fundamentals_snapshots table.

Revision ID: k7f8a9b0c1d2
Revises: j6e7f8a9b0c1
Create Date: 2026-08-11 09:20:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "k7f8a9b0c1d2"
down_revision: Union[str, Sequence[str], None] = "j6e7f8a9b0c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "annual_fundamentals_snapshots",
        sa.Column("annual_snapshot_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("identifier_type", sa.String(length=32), nullable=False),
        sa.Column("identifier", sa.String(length=64), nullable=False),
        sa.Column("security_id", sa.String(length=16), nullable=True),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("period_end_date", sa.Date(), nullable=False),
        # Balance sheet
        sa.Column("total_assets", sa.Numeric(20, 2), nullable=True),
        sa.Column("total_equity", sa.Numeric(20, 2), nullable=True),
        sa.Column("total_debt", sa.Numeric(20, 2), nullable=True),
        sa.Column("cash_and_equivalents", sa.Numeric(20, 2), nullable=True),
        sa.Column("finance_costs", sa.Numeric(20, 2), nullable=True),
        sa.Column("current_assets", sa.Numeric(20, 2), nullable=True),
        sa.Column("current_liabilities", sa.Numeric(20, 2), nullable=True),
        # Quality ratios
        sa.Column("roce", sa.Numeric(10, 4), nullable=True),
        sa.Column("roe", sa.Numeric(10, 4), nullable=True),
        sa.Column("roa", sa.Numeric(10, 4), nullable=True),
        sa.Column("debt_to_equity", sa.Numeric(10, 4), nullable=True),
        sa.Column("interest_coverage", sa.Numeric(10, 4), nullable=True),
        sa.Column("current_ratio", sa.Numeric(10, 4), nullable=True),
        # Metadata
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
        sa.PrimaryKeyConstraint("annual_snapshot_id"),
        sa.UniqueConstraint(
            "identifier_type",
            "identifier",
            "fiscal_year",
            name="uq_annual_fundamentals_identity",
        ),
    )
    op.create_index(
        "ix_annual_fundamentals_snapshots_identifier",
        "annual_fundamentals_snapshots",
        ["identifier_type", "identifier"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_annual_fundamentals_snapshots_identifier",
        table_name="annual_fundamentals_snapshots",
    )
    op.drop_table("annual_fundamentals_snapshots")
