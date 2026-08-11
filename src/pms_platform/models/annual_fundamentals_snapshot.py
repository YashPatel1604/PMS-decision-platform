"""Annual fundamentals snapshot ORM model — balance sheet and quality ratios."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from pms_platform.db.base import Base


class AnnualFundamentalsSnapshot(Base):
    """Balance-sheet derived quality metrics for one company-fiscal-year."""

    __tablename__ = "annual_fundamentals_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "identifier_type",
            "identifier",
            "fiscal_year",
            name="uq_annual_fundamentals_identity",
        ),
    )

    annual_snapshot_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    identifier_type: Mapped[str] = mapped_column(String(32), nullable=False)
    identifier: Mapped[str] = mapped_column(String(64), nullable=False)
    security_id: Mapped[str | None] = mapped_column(
        String(16), ForeignKey("securities.security_id", ondelete="SET NULL")
    )
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_end_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Balance sheet (₹ Cr)
    total_assets: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    total_equity: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    total_debt: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    cash_and_equivalents: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    finance_costs: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    current_assets: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    current_liabilities: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))

    # Quality ratios
    roce: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    roe: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    roa: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    debt_to_equity: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    interest_coverage: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    current_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))

    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
