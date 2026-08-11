"""Add valuation_snapshots table.

Revision ID: i5d6e7f8a9b0
Revises: h4c5d6e7f8a9
Create Date: 2026-08-11 09:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "i5d6e7f8a9b0"
down_revision: Union[str, Sequence[str], None] = "h4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "valuation_snapshots",
        sa.Column("valuation_snapshot_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("identifier_type", sa.String(length=32), nullable=False),
        sa.Column("identifier", sa.String(length=64), nullable=False),
        sa.Column("security_id", sa.String(length=16), nullable=True),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        # Valuation
        sa.Column("last_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("market_cap_cr", sa.Numeric(20, 2), nullable=True),
        sa.Column("pe_ratio", sa.Numeric(12, 4), nullable=True),
        sa.Column("industry_pe", sa.Numeric(12, 4), nullable=True),
        sa.Column("book_value_per_share", sa.Numeric(18, 4), nullable=True),
        sa.Column("price_to_book", sa.Numeric(12, 4), nullable=True),
        sa.Column("eps", sa.Numeric(18, 4), nullable=True),
        sa.Column("dividend_yield", sa.Numeric(10, 4), nullable=True),
        sa.Column("earnings_yield", sa.Numeric(10, 4), nullable=True),
        sa.Column("price_to_sales", sa.Numeric(12, 4), nullable=True),
        sa.Column("peg_ratio", sa.Numeric(12, 4), nullable=True),
        sa.Column("week_52_high", sa.Numeric(18, 4), nullable=True),
        sa.Column("week_52_low", sa.Numeric(18, 4), nullable=True),
        # Price returns
        sa.Column("return_1d_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("return_1m_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("return_3m_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("return_6m_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("return_1y_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("return_3y_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("all_time_high", sa.Numeric(18, 4), nullable=True),
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
        sa.PrimaryKeyConstraint("valuation_snapshot_id"),
        sa.UniqueConstraint(
            "identifier_type",
            "identifier",
            "as_of_date",
            name="uq_valuation_snapshot_identity",
        ),
    )
    op.create_index(
        "ix_valuation_snapshots_identifier",
        "valuation_snapshots",
        ["identifier_type", "identifier"],
    )
    op.create_index(
        "ix_valuation_snapshots_as_of_date",
        "valuation_snapshots",
        ["as_of_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_valuation_snapshots_as_of_date", table_name="valuation_snapshots")
    op.drop_index("ix_valuation_snapshots_identifier", table_name="valuation_snapshots")
    op.drop_table("valuation_snapshots")
