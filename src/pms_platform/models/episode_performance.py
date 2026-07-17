"""Episode ownership-period performance ORM model."""

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pms_platform.db.base import Base


class EpisodePerformance(Base):
    """Ownership-period performance metrics for one closed episode."""

    __tablename__ = "episode_performance"
    __table_args__ = (UniqueConstraint("episode_id", name="uq_episode_performance_episode_id"),)

    episode_performance_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    episode_id: Mapped[int] = mapped_column(
        ForeignKey("investment_episodes.episode_id"), nullable=False
    )
    security_id: Mapped[str] = mapped_column(ForeignKey("securities.security_id"), nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    exit_date: Mapped[date] = mapped_column(Date, nullable=False)
    holding_days: Mapped[int] = mapped_column(Integer, nullable=False)
    total_invested: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    total_sale_proceeds: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    dividends_received: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    total_profit_loss: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    total_return_pct: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    stock_xirr: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    smallcap_return_pct: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    smallcap_annualized_return: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    excess_vs_smallcap: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    benchmark_code: Mapped[str | None] = mapped_column(String(64))
    benchmark_start_level: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    benchmark_end_level: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    calculation_version: Mapped[str] = mapped_column(String(32), nullable=False)
    data_quality_status: Mapped[str] = mapped_column(String(32), nullable=False)
    data_quality_notes: Mapped[str | None] = mapped_column(Text)
