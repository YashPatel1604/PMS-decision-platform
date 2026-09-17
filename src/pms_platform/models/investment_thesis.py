"""Investment thesis and portfolio surveillance ORM models."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from pms_platform.db.base import Base


class InvestmentThesis(Base):
    """Versioned investment thesis — never overwrite prior versions."""

    __tablename__ = "investment_theses"
    __table_args__ = (
        UniqueConstraint("security_id", "version", name="uq_investment_thesis_version"),
    )

    thesis_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    security_id: Mapped[str] = mapped_column(
        ForeignKey("securities.security_id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", index=True)
    thesis_summary: Mapped[str | None] = mapped_column(Text)
    business_quality: Mapped[str | None] = mapped_column(Text)
    industry_thesis: Mapped[str | None] = mapped_column(Text)
    competitive_advantage: Mapped[str | None] = mapped_column(Text)
    management_thesis: Mapped[str | None] = mapped_column(Text)
    capital_allocation_thesis: Mapped[str | None] = mapped_column(Text)
    revenue_assumption: Mapped[str | None] = mapped_column(Text)
    margin_assumption: Mapped[str | None] = mapped_column(Text)
    earnings_assumption: Mapped[str | None] = mapped_column(Text)
    valuation_framework: Mapped[str | None] = mapped_column(Text)
    expected_holding_period: Mapped[str | None] = mapped_column(Text)
    bull_case: Mapped[str | None] = mapped_column(Text)
    base_case: Mapped[str | None] = mapped_column(Text)
    bear_case: Mapped[str | None] = mapped_column(Text)
    key_risks: Mapped[str | None] = mapped_column(Text)
    key_monitoring_variables: Mapped[str | None] = mapped_column(Text)
    disconfirming_evidence: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class PortfolioEvent(Base):
    """Surveillance event with human- or rule-set materiality (not LLM-alone)."""

    __tablename__ = "portfolio_events"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_portfolio_events_dedupe"),)

    event_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    security_id: Mapped[str | None] = mapped_column(
        ForeignKey("securities.security_id", ondelete="SET NULL"), nullable=True, index=True
    )
    company: Mapped[str | None] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_date: Mapped[date | None] = mapped_column(Date, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_document_reference: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    materiality: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    materiality_reason: Mapped[str] = mapped_column(Text, nullable=False)
    affected_thesis: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[str | None] = mapped_column(String(16))
    universe: Mapped[str] = mapped_column(String(16), nullable=False, default="other")
    dedupe_key: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ThesisConflictFlag(Base):
    """Human-review flag when evidence may conflict with an active thesis."""

    __tablename__ = "thesis_conflict_flags"

    flag_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    thesis_id: Mapped[int] = mapped_column(
        ForeignKey("investment_theses.thesis_id", ondelete="CASCADE"), nullable=False
    )
    security_id: Mapped[str] = mapped_column(
        ForeignKey("securities.security_id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("portfolio_events.event_id", ondelete="SET NULL"), nullable=True
    )
    assumption_affected: Mapped[str] = mapped_column(Text, nullable=False)
    what_changed: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    management_explanation: Mapped[str | None] = mapped_column(Text)
    investigate_next: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
