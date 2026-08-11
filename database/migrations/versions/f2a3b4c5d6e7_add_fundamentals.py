"""Add quarterly fundamentals and computed snapshot tables.

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-08-10 14:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, Sequence[str], None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "company_fundamentals_quarterly",
        sa.Column("fundamental_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("identifier_type", sa.String(length=32), nullable=False),
        sa.Column("identifier", sa.String(length=64), nullable=False),
        sa.Column("security_id", sa.String(length=16), nullable=True),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("fiscal_quarter", sa.String(length=8), nullable=False),
        sa.Column("period_end_date", sa.Date(), nullable=False),
        sa.Column("sales", sa.Numeric(20, 2), nullable=True),
        sa.Column("ebitda", sa.Numeric(20, 2), nullable=True),
        sa.Column("ebit", sa.Numeric(20, 2), nullable=True),
        sa.Column("pat", sa.Numeric(20, 2), nullable=True),
        sa.Column("opm", sa.Numeric(8, 4), nullable=True),
        sa.Column("npm", sa.Numeric(8, 4), nullable=True),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("contract_version", sa.String(length=16), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_file", sa.String(length=512), nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=False),
        sa.Column("source_key", sa.String(length=768), nullable=False),
        sa.Column("import_batch_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["import_batch_id"],
            ["import_batches.import_batch_id"],
        ),
        sa.ForeignKeyConstraint(
            ["security_id"],
            ["securities.security_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("fundamental_id"),
        sa.UniqueConstraint("source_key", name="uq_fundamentals_quarterly_source_key"),
        sa.UniqueConstraint(
            "identifier_type",
            "identifier",
            "period_end_date",
            "source",
            name="uq_fundamentals_quarterly_identity",
        ),
    )
    op.create_index(
        "ix_fundamentals_quarterly_identifier",
        "company_fundamentals_quarterly",
        ["identifier_type", "identifier"],
    )
    op.create_index(
        "ix_fundamentals_quarterly_period",
        "company_fundamentals_quarterly",
        ["period_end_date"],
    )

    op.create_table(
        "fundamental_snapshots",
        sa.Column("snapshot_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("identifier_type", sa.String(length=32), nullable=False),
        sa.Column("identifier", sa.String(length=64), nullable=False),
        sa.Column("security_id", sa.String(length=16), nullable=True),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("fiscal_quarter", sa.String(length=8), nullable=False),
        sa.Column("period_end_date", sa.Date(), nullable=False),
        sa.Column("sales", sa.Numeric(20, 2), nullable=True),
        sa.Column("pat", sa.Numeric(20, 2), nullable=True),
        sa.Column("opm", sa.Numeric(8, 4), nullable=True),
        sa.Column("npm", sa.Numeric(8, 4), nullable=True),
        sa.Column("sales_yoy_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("sales_qoq_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("pat_yoy_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("opm_delta_pp", sa.Numeric(10, 4), nullable=True),
        sa.Column("npm_delta_pp", sa.Numeric(10, 4), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("computation_version", sa.String(length=16), nullable=False),
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
        sa.PrimaryKeyConstraint("snapshot_id"),
        sa.UniqueConstraint(
            "identifier_type",
            "identifier",
            "period_end_date",
            "computation_version",
            name="uq_fundamental_snapshot_identity",
        ),
    )
    op.create_index(
        "ix_fundamental_snapshots_identifier",
        "fundamental_snapshots",
        ["identifier_type", "identifier"],
    )


def downgrade() -> None:
    op.drop_index("ix_fundamental_snapshots_identifier", table_name="fundamental_snapshots")
    op.drop_table("fundamental_snapshots")
    op.drop_index("ix_fundamentals_quarterly_period", table_name="company_fundamentals_quarterly")
    op.drop_index(
        "ix_fundamentals_quarterly_identifier",
        table_name="company_fundamentals_quarterly",
    )
    op.drop_table("company_fundamentals_quarterly")
