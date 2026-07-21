"""Standardized post-exit horizon performance ORM model."""

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pms_platform.db.base import Base


class PostExitHorizonPerformance(Base):
    """Stock and comparator returns at a fixed post-exit horizon."""

    __tablename__ = "post_exit_horizon_performance"
    __table_args__ = (
        UniqueConstraint(
            "episode_id",
            "horizon",
            name="uq_post_exit_horizon_episode_horizon",
        ),
    )

    post_exit_horizon_performance_id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    episode_id: Mapped[int] = mapped_column(
        ForeignKey("investment_episodes.episode_id"),
        nullable=False,
    )
    horizon: Mapped[str] = mapped_column(String(16), nullable=False)
    exit_date: Mapped[date] = mapped_column(Date, nullable=False)
    target_date: Mapped[date | None] = mapped_column(Date)
    comparison_date: Mapped[date | None] = mapped_column(Date)
    days_after_exit: Mapped[int | None]
    security_return_after_exit: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    smallcap_return_after_exit: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    excess_vs_smallcap_after_exit: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    provisional_portfolio_return_after_exit: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6)
    )
    provisional_excess_vs_portfolio_after_exit: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6)
    )
    calculation_version: Mapped[str] = mapped_column(String(32), nullable=False)
    data_quality_status: Mapped[str] = mapped_column(String(32), nullable=False)
