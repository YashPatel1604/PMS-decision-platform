"""Computed fundamental snapshot ORM model."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from pms_platform.db.base import Base


class FundamentalSnapshot(Base):
    """Computed growth/margin metrics for one company-quarter."""

    __tablename__ = "fundamental_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "identifier_type",
            "identifier",
            "period_end_date",
            "computation_version",
            name="uq_fundamental_snapshot_identity",
        ),
    )

    snapshot_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    identifier_type: Mapped[str] = mapped_column(String(32), nullable=False)
    identifier: Mapped[str] = mapped_column(String(64), nullable=False)
    security_id: Mapped[str | None] = mapped_column(
        String(16), ForeignKey("securities.security_id", ondelete="SET NULL")
    )
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    fiscal_quarter: Mapped[str] = mapped_column(String(8), nullable=False)
    period_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    sales: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    pat: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    opm: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    npm: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    sales_yoy_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    sales_qoq_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    pat_yoy_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    opm_delta_pp: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    npm_delta_pp: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    sales_3y_cagr: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    sales_5y_cagr: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    pat_3y_cagr: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    pat_5y_cagr: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    computation_version: Mapped[str] = mapped_column(String(16), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
