"""Liquid holding transaction ORM model."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from pms_platform.db.base import Base


class LiquidTransaction(Base):
    """LiquidCase or equivalent liquid balance movement."""

    __tablename__ = "liquid_transactions"
    __table_args__ = (UniqueConstraint("source_key", name="uq_liquid_transactions_source_key"),)

    liquid_transaction_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    source_file: Mapped[str] = mapped_column(String(512), nullable=False)
    source_sheet: Mapped[str] = mapped_column(String(128), nullable=False)
    source_row: Mapped[int] = mapped_column(Integer, nullable=False)
    source_note: Mapped[str | None] = mapped_column(Text)
    source_key: Mapped[str] = mapped_column(String(768), nullable=False)
    import_batch_id: Mapped[int] = mapped_column(
        ForeignKey("import_batches.import_batch_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
