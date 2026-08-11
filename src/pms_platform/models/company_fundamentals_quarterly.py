"""Quarterly company fundamentals ORM model."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pms_platform.db.base import Base


class CompanyFundamentalsQuarterly(Base):
    """One row of quarterly financial facts for a company."""

    __tablename__ = "company_fundamentals_quarterly"
    __table_args__ = (
        UniqueConstraint("source_key", name="uq_fundamentals_quarterly_source_key"),
        UniqueConstraint(
            "identifier_type",
            "identifier",
            "period_end_date",
            "source",
            name="uq_fundamentals_quarterly_identity",
        ),
    )

    fundamental_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    identifier_type: Mapped[str] = mapped_column(String(32), nullable=False)
    identifier: Mapped[str] = mapped_column(String(64), nullable=False)
    security_id: Mapped[str | None] = mapped_column(
        String(16), ForeignKey("securities.security_id", ondelete="SET NULL")
    )
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    fiscal_quarter: Mapped[str] = mapped_column(String(8), nullable=False)
    period_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    sales: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    ebitda: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    ebit: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    pat: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    opm: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    npm: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    contract_version: Mapped[str] = mapped_column(String(16), nullable=False)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_file: Mapped[str] = mapped_column(String(512), nullable=False)
    source_row: Mapped[int] = mapped_column(Integer, nullable=False)
    source_key: Mapped[str] = mapped_column(String(768), nullable=False)
    import_batch_id: Mapped[int] = mapped_column(
        ForeignKey("import_batches.import_batch_id"), nullable=False
    )
