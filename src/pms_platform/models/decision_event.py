"""Decision event ORM model."""

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pms_platform.db.base import Base


class DecisionEvent(Base):
    """Deterministic investment decision derived from transactions."""

    __tablename__ = "decision_events"

    decision_event_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    episode_id: Mapped[int] = mapped_column(
        ForeignKey("investment_episodes.episode_id"), nullable=False
    )
    security_id: Mapped[str] = mapped_column(ForeignKey("securities.security_id"), nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    decision_type: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity_change: Mapped[int] = mapped_column(Integer, nullable=False)
    position_before: Mapped[int] = mapped_column(Integer, nullable=False)
    position_after: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    source_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.transaction_id")
    )

    episode = relationship("InvestmentEpisode", back_populates="decision_events")
