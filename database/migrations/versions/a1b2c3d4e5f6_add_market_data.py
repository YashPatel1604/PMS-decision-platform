"""add market data tables

Revision ID: a1b2c3d4e5f6
Revises: cc35ac3f8e16
Create Date: 2026-07-17 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "cc35ac3f8e16"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "daily_prices",
        sa.Column("daily_price_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("security_id", sa.String(length=16), nullable=True),
        sa.Column("identifier_type", sa.String(length=32), nullable=False),
        sa.Column("identifier", sa.String(length=64), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("close", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("adjusted_close", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("adjustment_basis", sa.String(length=64), nullable=False),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("publication_date", sa.Date(), nullable=True),
        sa.Column("source_file", sa.String(length=512), nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=False),
        sa.Column("source_key", sa.String(length=768), nullable=False),
        sa.Column("import_batch_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["import_batch_id"], ["import_batches.import_batch_id"]),
        sa.ForeignKeyConstraint(["security_id"], ["securities.security_id"]),
        sa.PrimaryKeyConstraint("daily_price_id"),
        sa.UniqueConstraint(
            "security_id",
            "trade_date",
            "source",
            name="uq_daily_prices_security_date_source",
        ),
        sa.UniqueConstraint("source_key", name="uq_daily_prices_source_key"),
    )
    op.create_table(
        "dividends",
        sa.Column("dividend_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("security_id", sa.String(length=16), nullable=True),
        sa.Column("identifier_type", sa.String(length=32), nullable=False),
        sa.Column("identifier", sa.String(length=64), nullable=False),
        sa.Column("ex_date", sa.Date(), nullable=False),
        sa.Column("record_date", sa.Date(), nullable=True),
        sa.Column("payment_date", sa.Date(), nullable=True),
        sa.Column("dividend_per_share", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("publication_date", sa.Date(), nullable=True),
        sa.Column("source_file", sa.String(length=512), nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=False),
        sa.Column("source_key", sa.String(length=768), nullable=False),
        sa.Column("import_batch_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["import_batch_id"], ["import_batches.import_batch_id"]),
        sa.ForeignKeyConstraint(["security_id"], ["securities.security_id"]),
        sa.PrimaryKeyConstraint("dividend_id"),
        sa.UniqueConstraint(
            "security_id",
            "ex_date",
            "source",
            name="uq_dividends_security_ex_date_source",
        ),
        sa.UniqueConstraint("source_key", name="uq_dividends_source_key"),
    )
    op.create_table(
        "benchmark_tri",
        sa.Column("benchmark_tri_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("benchmark_code", sa.String(length=64), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("tri_level", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("publication_date", sa.Date(), nullable=True),
        sa.Column("methodology_version", sa.String(length=64), nullable=True),
        sa.Column("source_file", sa.String(length=512), nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=False),
        sa.Column("source_key", sa.String(length=768), nullable=False),
        sa.Column("import_batch_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["import_batch_id"], ["import_batches.import_batch_id"]),
        sa.PrimaryKeyConstraint("benchmark_tri_id"),
        sa.UniqueConstraint(
            "benchmark_code",
            "trade_date",
            "source",
            name="uq_benchmark_tri_code_date_source",
        ),
        sa.UniqueConstraint("source_key", name="uq_benchmark_tri_source_key"),
    )
    op.create_table(
        "security_symbol_history",
        sa.Column("symbol_history_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("security_id", sa.String(length=16), nullable=False),
        sa.Column("symbol_type", sa.String(length=16), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("source_file", sa.String(length=512), nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=False),
        sa.Column("source_key", sa.String(length=768), nullable=False),
        sa.Column("import_batch_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["import_batch_id"], ["import_batches.import_batch_id"]),
        sa.ForeignKeyConstraint(["security_id"], ["securities.security_id"]),
        sa.PrimaryKeyConstraint("symbol_history_id"),
        sa.UniqueConstraint(
            "security_id",
            "symbol_type",
            "symbol",
            "effective_from",
            name="uq_security_symbol_history_identity",
        ),
        sa.UniqueConstraint("source_key", name="uq_security_symbol_history_source_key"),
    )
    op.create_table(
        "security_successors",
        sa.Column("successor_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("predecessor_security_id", sa.String(length=16), nullable=False),
        sa.Column("successor_security_id", sa.String(length=16), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column("confirmed", sa.Boolean(), nullable=False),
        sa.Column("source_file", sa.String(length=512), nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=False),
        sa.Column("source_key", sa.String(length=768), nullable=False),
        sa.Column("import_batch_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["import_batch_id"], ["import_batches.import_batch_id"]),
        sa.ForeignKeyConstraint(["predecessor_security_id"], ["securities.security_id"]),
        sa.ForeignKeyConstraint(["successor_security_id"], ["securities.security_id"]),
        sa.PrimaryKeyConstraint("successor_id"),
        sa.UniqueConstraint(
            "predecessor_security_id",
            "successor_security_id",
            "effective_date",
            "action_type",
            name="uq_security_successors_chain",
        ),
        sa.UniqueConstraint("source_key", name="uq_security_successors_source_key"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("security_successors")
    op.drop_table("security_symbol_history")
    op.drop_table("benchmark_tri")
    op.drop_table("dividends")
    op.drop_table("daily_prices")
