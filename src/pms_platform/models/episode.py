"""Investment episode ORM model."""

from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pms_platform.db.base import Base


class InvestmentEpisode(Base):
    """One contiguous holding period for a security."""

    __tablename__ = "investment_episodes"

    episode_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    security_id: Mapped[str] = mapped_column(ForeignKey("securities.security_id"), nullable=False)
    episode_number: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    exit_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    initial_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    total_buy_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_sell_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    corporate_action_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    final_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    number_of_buys: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    number_of_sells: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    decision_events = relationship("DecisionEvent", back_populates="episode")
