"""Episode cash-flow ORM model."""

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from pms_platform.db.base import Base


class EpisodeCashFlowRecord(Base):
    """Persisted dated cash flow used for episode XIRR."""

    __tablename__ = "episode_cash_flows"

    episode_cash_flow_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    episode_id: Mapped[int] = mapped_column(
        ForeignKey("investment_episodes.episode_id"), nullable=False
    )
    flow_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    flow_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    source_reference: Mapped[str | None] = mapped_column(String(64))
    calculation_version: Mapped[str] = mapped_column(String(32), nullable=False)
