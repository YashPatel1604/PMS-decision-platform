"""Watchlist ORM models."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pms_platform.db.base import Base


class Watchlist(Base):
    """Named collection of stocks to track outside the live portfolio."""

    __tablename__ = "watchlists"

    watchlist_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    members = relationship(
        "WatchlistMember",
        back_populates="watchlist",
        cascade="all, delete-orphan",
        order_by="WatchlistMember.added_at",
    )


class WatchlistMember(Base):
    """One stock on a watchlist."""

    __tablename__ = "watchlist_members"
    __table_args__ = (
        UniqueConstraint(
            "watchlist_id",
            "security_id",
            name="uq_watchlist_member_security",
        ),
    )

    member_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    watchlist_id: Mapped[int] = mapped_column(
        ForeignKey("watchlists.watchlist_id", ondelete="CASCADE"),
        nullable=False,
    )
    security_id: Mapped[str | None] = mapped_column(
        ForeignKey("securities.security_id", ondelete="SET NULL"),
        nullable=True,
    )
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    nse_symbol: Mapped[str | None] = mapped_column(String(32))
    bse_code: Mapped[str | None] = mapped_column(String(16))
    isin: Mapped[str | None] = mapped_column(String(16))
    notes: Mapped[str | None] = mapped_column(Text)
    resolution_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="PENDING"
    )
    resolution_source: Mapped[str | None] = mapped_column(String(16))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    watchlist = relationship("Watchlist", back_populates="members")
    security = relationship("Security")


class WatchlistResolutionLog(Base):
    """Audit log for failed or retried symbol resolution attempts."""

    __tablename__ = "watchlist_resolution_logs"

    log_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    watchlist_id: Mapped[int] = mapped_column(
        ForeignKey("watchlists.watchlist_id", ondelete="CASCADE"),
        nullable=False,
    )
    member_id: Mapped[int | None] = mapped_column(
        ForeignKey("watchlist_members.member_id", ondelete="SET NULL"),
        nullable=True,
    )
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    source_attempted: Mapped[str | None] = mapped_column(String(16))
    message: Mapped[str] = mapped_column(Text, nullable=False)


class WatchlistAlert(Base):
    """SAST or insider disclosure alert scoped to one watchlist."""

    __tablename__ = "watchlist_alerts"
    __table_args__ = (
        UniqueConstraint(
            "watchlist_id",
            "dedupe_key",
            name="uq_watchlist_alert_dedupe",
        ),
    )

    alert_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    watchlist_id: Mapped[int] = mapped_column(
        ForeignKey("watchlists.watchlist_id", ondelete="CASCADE"),
        nullable=False,
    )
    member_id: Mapped[int | None] = mapped_column(
        ForeignKey("watchlist_members.member_id", ondelete="SET NULL"),
        nullable=True,
    )
    dedupe_key: Mapped[str] = mapped_column(String(512), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    disclosure_date: Mapped[date] = mapped_column(Date, nullable=False)
    bse_code: Mapped[str] = mapped_column(String(16), nullable=False)
    company_name: Mapped[str] = mapped_column(String(256), nullable=False)
    person_name: Mapped[str] = mapped_column(String(256), nullable=False)
    category: Mapped[str] = mapped_column(String(128), nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(128), nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    value: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    pct_pre: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    pct_post: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    mode: Mapped[str] = mapped_column(String(128), nullable=False)
    regulation: Mapped[str] = mapped_column(String(64), nullable=False)
    market_cap_cr: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    watchlist = relationship("Watchlist")
    member = relationship("WatchlistMember")
