"""Promoter shareholding snapshot ORM model."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from pms_platform.db.base import Base


class PromoterSnapshot(Base):
    """Latest promoter holding and pledging data for one company-quarter."""

    __tablename__ = "promoter_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "identifier_type",
            "identifier",
            "quarter_end_date",
            name="uq_promoter_snapshot_identity",
        ),
    )

    promoter_snapshot_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    identifier_type: Mapped[str] = mapped_column(String(32), nullable=False)
    identifier: Mapped[str] = mapped_column(String(64), nullable=False)
    security_id: Mapped[str | None] = mapped_column(
        String(16), ForeignKey("securities.security_id", ondelete="SET NULL")
    )
    quarter_end_date: Mapped[date] = mapped_column(Date, nullable=False)

    promoter_holding_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    promoter_holding_change_pp: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    pledged_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))

    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
