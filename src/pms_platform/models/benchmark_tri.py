"""Benchmark total-return index ORM model."""

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pms_platform.db.base import Base


class BenchmarkTri(Base):
    """Daily benchmark total-return index level."""

    __tablename__ = "benchmark_tri"
    __table_args__ = (
        UniqueConstraint(
            "benchmark_code",
            "trade_date",
            "source",
            name="uq_benchmark_tri_code_date_source",
        ),
        UniqueConstraint("source_key", name="uq_benchmark_tri_source_key"),
    )

    benchmark_tri_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    benchmark_code: Mapped[str] = mapped_column(String(64), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    tri_level: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    publication_date: Mapped[date | None] = mapped_column(Date)
    methodology_version: Mapped[str | None] = mapped_column(String(64))
    source_file: Mapped[str] = mapped_column(String(512), nullable=False)
    source_row: Mapped[int] = mapped_column(Integer, nullable=False)
    source_key: Mapped[str] = mapped_column(String(768), nullable=False)
    import_batch_id: Mapped[int] = mapped_column(
        ForeignKey("import_batches.import_batch_id"), nullable=False
    )
