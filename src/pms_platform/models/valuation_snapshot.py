"""Valuation snapshot ORM model — live price, P/E, P/B, returns, etc."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from pms_platform.db.base import Base


class ValuationSnapshot(Base):
    """Daily valuation metrics for one company, sourced from BSE and price history."""

    __tablename__ = "valuation_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "identifier_type",
            "identifier",
            "as_of_date",
            name="uq_valuation_snapshot_identity",
        ),
    )

    valuation_snapshot_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    identifier_type: Mapped[str] = mapped_column(String(32), nullable=False)
    identifier: Mapped[str] = mapped_column(String(64), nullable=False)
    security_id: Mapped[str | None] = mapped_column(
        String(16), ForeignKey("securities.security_id", ondelete="SET NULL")
    )
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)

    # --- Valuation (BSE StockTrading) ---
    last_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    market_cap_cr: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    pe_ratio: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    industry_pe: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    book_value_per_share: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    price_to_book: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    eps: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    dividend_yield: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    earnings_yield: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    price_to_sales: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    peg_ratio: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    week_52_high: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    week_52_low: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))

    # --- Price returns (from daily_prices) ---
    return_1d_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    return_1m_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    return_3m_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    return_6m_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    return_1y_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    return_3y_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    all_time_high: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))

    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
