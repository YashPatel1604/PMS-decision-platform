"""Dated security symbol history ORM model."""

from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pms_platform.db.base import Base


class SecuritySymbolHistory(Base):
    """Historical symbol mapping for a security over time."""

    __tablename__ = "security_symbol_history"
    __table_args__ = (
        UniqueConstraint(
            "security_id",
            "symbol_type",
            "symbol",
            "effective_from",
            name="uq_security_symbol_history_identity",
        ),
        UniqueConstraint("source_key", name="uq_security_symbol_history_source_key"),
    )

    symbol_history_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    security_id: Mapped[str] = mapped_column(ForeignKey("securities.security_id"), nullable=False)
    symbol_type: Mapped[str] = mapped_column(String(16), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    source_file: Mapped[str] = mapped_column(String(512), nullable=False)
    source_row: Mapped[int] = mapped_column(Integer, nullable=False)
    source_key: Mapped[str] = mapped_column(String(768), nullable=False)
    import_batch_id: Mapped[int] = mapped_column(
        ForeignKey("import_batches.import_batch_id"), nullable=False
    )
