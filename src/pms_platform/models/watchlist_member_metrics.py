"""Materialized screener metrics per watchlist member (read path for UI)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pms_platform.db.base import Base

_METRICS_JSON = JSON().with_variant(JSONB, "postgresql")


class WatchlistMemberMetrics(Base):
    """Pre-joined metrics for one watchlist member — rebuilt after refresh jobs."""

    __tablename__ = "watchlist_member_metrics"

    member_id: Mapped[int] = mapped_column(
        ForeignKey("watchlist_members.member_id", ondelete="CASCADE"),
        primary_key=True,
    )
    watchlist_id: Mapped[int] = mapped_column(
        ForeignKey("watchlists.watchlist_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    computation_version: Mapped[str] = mapped_column(String(16), nullable=False)
    fiscal_year: Mapped[int | None] = mapped_column(Integer)
    fiscal_quarter: Mapped[str | None] = mapped_column(String(8))
    period_end_date: Mapped[date | None] = mapped_column(Date)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    has_fundamentals: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fundamentals_stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(_METRICS_JSON, nullable=False, default=dict)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
