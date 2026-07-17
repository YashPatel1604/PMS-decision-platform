"""Post-exit performance ORM model."""

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pms_platform.db.base import Base


class PostExitPerformance(Base):
    """Performance from final sell date to the latest available comparison date."""

    __tablename__ = "post_exit_performance"
    __table_args__ = (UniqueConstraint("episode_id", name="uq_post_exit_performance_episode_id"),)

    post_exit_performance_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    episode_id: Mapped[int] = mapped_column(
        ForeignKey("investment_episodes.episode_id"), nullable=False
    )
    exit_date: Mapped[date] = mapped_column(Date, nullable=False)
    comparison_date: Mapped[date | None] = mapped_column(Date)
    security_return_after_exit: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    portfolio_return_after_exit: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    smallcap_return_after_exit: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    excess_vs_portfolio_after_exit: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    excess_vs_smallcap_after_exit: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    maximum_gain_after_exit: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    maximum_loss_after_exit: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    calculation_version: Mapped[str] = mapped_column(String(32), nullable=False)
    data_quality_status: Mapped[str] = mapped_column(String(32), nullable=False)
