"""NSE CM bhav bars, import runs, and pivot-strategy portfolio symbols."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pms_platform.db.base import Base

_JSON = JSON().with_variant(JSONB, "postgresql")


class BhavImportRun(Base):
    """One staged/validated/committed daily bhav upload."""

    __tablename__ = "bhav_import_runs"

    run_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trade_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    staged_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    source_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="staged")
    row_count_all: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    row_count_eq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    validation_report: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False, default=dict)
    reconcile_report: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NseBhavBar(Base):
    """One NSE CM bhav OHLC row for a trade date / symbol / series."""

    __tablename__ = "nse_bhav_bars"
    __table_args__ = (
        UniqueConstraint(
            "trade_date",
            "symbol",
            "series",
            name="uq_nse_bhav_bars_date_symbol_series",
        ),
        UniqueConstraint("source_key", name="uq_nse_bhav_bars_source_key"),
    )

    bar_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    series: Mapped[str] = mapped_column(String(16), nullable=False, default="EQ")
    isin: Mapped[str | None] = mapped_column(String(32), nullable=True)
    instrument_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    open: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    prev_close: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    turnover: Mapped[Decimal | None] = mapped_column(Numeric(24, 2), nullable=True)
    source_key: Mapped[str] = mapped_column(String(256), nullable=False)
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("bhav_import_runs.run_id"), nullable=True
    )


class PivotPortfolioSymbol(Base):
    """Symbols tracked on the Pivot Point Strategy portfolio sheet."""

    __tablename__ = "pivot_portfolio_symbols"

    symbol: Mapped[str] = mapped_column(String(64), primary_key=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dummy: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    portfolio_a: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    uptrend: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    support_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    buy_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    sma_50: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sma_100: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sma_200: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class PivotVolExp(Base):
    """Per-symbol Vol Exp for one as-of day (Last20 avg ×1.1 top50 / ×1.2 else)."""

    __tablename__ = "pivot_vol_exp"

    as_of_date: Mapped[date] = mapped_column(Date, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(64), primary_key=True)
    vol_exp: Mapped[Decimal] = mapped_column(Numeric(24, 4), nullable=False)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="last20")
