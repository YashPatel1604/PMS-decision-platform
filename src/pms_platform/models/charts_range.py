"""Approved Charts Range row values (replaces live Excel writes when workflow enabled)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from pms_platform.db.base import Base


class ChartsRangeRow(Base):
    __tablename__ = "charts_range_rows"

    excel_row: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    section: Mapped[str] = mapped_column(String(16), nullable=False, default="holdings")
    high: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    low: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    close_override: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    weekly_close: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    support_resistance: Mapped[str | None] = mapped_column(Text)
    weekly_close_date: Mapped[str | None] = mapped_column(String(32))
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
