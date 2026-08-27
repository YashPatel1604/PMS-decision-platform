"""Firm-wide Pivot daily selection (replaces pivot-selected-firms localStorage)."""

from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from pms_platform.db.base import Base


class PivotFirmSelection(Base):
    """Ordered symbols checked in Pivot Daily 'selected' scope (firm-canonical)."""

    __tablename__ = "pivot_firm_selection"

    symbol: Mapped[str] = mapped_column(String(64), primary_key=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
