"""Add NSE bhav bars, import runs, and pivot portfolio symbols.

Revision ID: p2e3f4a5b6c7
Revises: o1d2e3f4a5b6
Create Date: 2026-08-20 19:20:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "p2e3f4a5b6c7"
down_revision: Union[str, Sequence[str], None] = "o1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bhav_import_runs",
        sa.Column("run_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=True),
        sa.Column("staged_path", sa.String(length=1024), nullable=False),
        sa.Column("source_filename", sa.String(length=512), nullable=False),
        sa.Column("source_checksum", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="staged"),
        sa.Column("row_count_all", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("row_count_eq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "validation_report",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "reconcile_report",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_table(
        "nse_bhav_bars",
        sa.Column("bar_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("series", sa.String(length=16), nullable=False),
        sa.Column("isin", sa.String(length=32), nullable=True),
        sa.Column("instrument_name", sa.String(length=256), nullable=True),
        sa.Column("open", sa.Numeric(18, 4), nullable=False),
        sa.Column("high", sa.Numeric(18, 4), nullable=False),
        sa.Column("low", sa.Numeric(18, 4), nullable=False),
        sa.Column("close", sa.Numeric(18, 4), nullable=False),
        sa.Column("prev_close", sa.Numeric(18, 4), nullable=True),
        sa.Column("volume", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("turnover", sa.Numeric(24, 2), nullable=True),
        sa.Column("source_key", sa.String(length=256), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["bhav_import_runs.run_id"]),
        sa.PrimaryKeyConstraint("bar_id"),
        sa.UniqueConstraint(
            "trade_date",
            "symbol",
            "series",
            name="uq_nse_bhav_bars_date_symbol_series",
        ),
        sa.UniqueConstraint("source_key", name="uq_nse_bhav_bars_source_key"),
    )
    op.create_index("ix_nse_bhav_bars_trade_date", "nse_bhav_bars", ["trade_date"])
    op.create_index("ix_nse_bhav_bars_symbol", "nse_bhav_bars", ["symbol"])
    op.create_table(
        "pivot_portfolio_symbols",
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("dummy", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("portfolio_a", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("uptrend", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("support_note", sa.Text(), nullable=True),
        sa.Column("buy_note", sa.Text(), nullable=True),
        sa.Column("sma_50", sa.String(length=64), nullable=True),
        sa.Column("sma_100", sa.String(length=64), nullable=True),
        sa.Column("sma_200", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("symbol"),
    )


def downgrade() -> None:
    op.drop_table("pivot_portfolio_symbols")
    op.drop_index("ix_nse_bhav_bars_symbol", table_name="nse_bhav_bars")
    op.drop_index("ix_nse_bhav_bars_trade_date", table_name="nse_bhav_bars")
    op.drop_table("nse_bhav_bars")
    op.drop_table("bhav_import_runs")
