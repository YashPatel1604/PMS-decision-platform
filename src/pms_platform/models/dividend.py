"""Dividend event ORM model."""

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pms_platform.db.base import Base


class Dividend(Base):
    """Dividend event imported from canonical CSV."""

    __tablename__ = "dividends"
    __table_args__ = (
        UniqueConstraint(
            "security_id",
            "ex_date",
            "source",
            name="uq_dividends_security_ex_date_source",
        ),
        UniqueConstraint("source_key", name="uq_dividends_source_key"),
    )

    dividend_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    security_id: Mapped[str | None] = mapped_column(
        ForeignKey("securities.security_id"), nullable=True
    )
    identifier_type: Mapped[str] = mapped_column(String(32), nullable=False)
    identifier: Mapped[str] = mapped_column(String(64), nullable=False)
    ex_date: Mapped[date] = mapped_column(Date, nullable=False)
    record_date: Mapped[date | None] = mapped_column(Date)
    payment_date: Mapped[date | None] = mapped_column(Date)
    dividend_per_share: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    publication_date: Mapped[date | None] = mapped_column(Date)
    source_file: Mapped[str] = mapped_column(String(512), nullable=False)
    source_row: Mapped[int] = mapped_column(Integer, nullable=False)
    source_key: Mapped[str] = mapped_column(String(768), nullable=False)
    import_batch_id: Mapped[int] = mapped_column(
        ForeignKey("import_batches.import_batch_id"), nullable=False
    )
