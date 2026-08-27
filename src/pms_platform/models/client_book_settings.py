"""Per-book settings (e.g. SCA bank balance) when approval workflow is enabled."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from pms_platform.db.base import Base


class ClientBookSettings(Base):
    __tablename__ = "client_book_settings"

    book: Mapped[str] = mapped_column(String(16), primary_key=True)
    bank_balance: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
