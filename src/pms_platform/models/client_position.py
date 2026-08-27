"""Approved client portfolio positions (canonical when approval workflow enabled)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from pms_platform.db.base import Base


class ClientPosition(Base):
    __tablename__ = "client_positions"
    __table_args__ = (UniqueConstraint("book", "symbol", name="uq_client_positions_book_symbol"),)

    client_position_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    book: Mapped[str] = mapped_column(String(16), nullable=False, default="client")
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
