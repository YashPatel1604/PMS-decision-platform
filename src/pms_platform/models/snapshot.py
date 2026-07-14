"""Portfolio snapshot ORM model."""

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pms_platform.db.base import Base


class PortfolioSnapshotRecord(Base):
    """Historical portfolio snapshot row imported from annual workbooks."""

    __tablename__ = "portfolio_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_date",
            "source_file",
            "source_sheet",
            "source_row",
            name="uq_portfolio_snapshots_source",
        ),
    )

    snapshot_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    security_id: Mapped[str | None] = mapped_column(ForeignKey("securities.security_id"))
    portfolio_name: Mapped[str] = mapped_column(String(128), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    market_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    market_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    portfolio_weight: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    source_file: Mapped[str] = mapped_column(String(512), nullable=False)
    source_sheet: Mapped[str] = mapped_column(String(128), nullable=False)
    source_row: Mapped[int] = mapped_column(Integer, nullable=False)
    import_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_batches.import_batch_id")
    )
