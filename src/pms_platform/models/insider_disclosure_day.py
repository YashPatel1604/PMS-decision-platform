"""Cached BSE insider-trading filings for one calendar day."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Integer, JSON, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pms_platform.db.base import Base

_ROWS_JSON = JSON().with_variant(JSONB, "postgresql")


class InsiderDisclosureDay(Base):
    """One BSE search day. Empty days are stored too so we do not refetch them."""

    __tablename__ = "insider_disclosure_days"

    disclosure_date: Mapped[date] = mapped_column(Date, primary_key=True)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rows: Mapped[list[dict[str, Any]]] = mapped_column(
        _ROWS_JSON, nullable=False, default=list
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
