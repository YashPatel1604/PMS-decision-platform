"""Watchlist refresh lock ORM model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from pms_platform.db.base import Base


class WatchlistRefreshLock(Base):
    """Prevents concurrent refresh on the same watchlist."""

    __tablename__ = "watchlist_refresh_locks"

    watchlist_id: Mapped[int] = mapped_column(
        ForeignKey("watchlists.watchlist_id", ondelete="CASCADE"),
        primary_key=True,
    )
    locked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
