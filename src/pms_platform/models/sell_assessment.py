"""Sell-quality assessment ORM model."""

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pms_platform.db.base import Base


class SellAssessment(Base):
    """Explainable exit-quality label for a closed episode."""

    __tablename__ = "sell_assessments"
    __table_args__ = (UniqueConstraint("episode_id", name="uq_sell_assessments_episode_id"),)

    sell_assessment_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    episode_id: Mapped[int] = mapped_column(
        ForeignKey("investment_episodes.episode_id"), nullable=False
    )
    exit_assessment: Mapped[str] = mapped_column(String(64), nullable=False)
    assessment_flags: Mapped[str | None] = mapped_column(String(256))
    assessment_reason: Mapped[str] = mapped_column(Text, nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(32), nullable=False)
    data_quality_status: Mapped[str] = mapped_column(String(32), nullable=False)
