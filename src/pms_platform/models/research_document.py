"""Research document index ORM models (files stay on disk; text + FTS in DB)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from pms_platform.db.base import Base


class ResearchDocument(Base):
    """Indexed research file metadata (original bytes remain on disk)."""

    __tablename__ = "research_documents"
    __table_args__ = (
        UniqueConstraint("source_root", "relative_path", name="uq_research_doc_path"),
    )

    document_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_root: Mapped[str] = mapped_column(String(32), nullable=False, default="research")
    mime_type: Mapped[str | None] = mapped_column(String(128))
    byte_size: Mapped[int | None] = mapped_column(BigInteger)
    mtime_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    title: Mapped[str | None] = mapped_column(Text)
    indexed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    parse_status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")
    parse_error: Mapped[str | None] = mapped_column(Text)
    security_id: Mapped[str | None] = mapped_column(
        ForeignKey("securities.security_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    pages = relationship(
        "ResearchDocumentPage",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="ResearchDocumentPage.page_number",
    )


class ResearchDocumentPage(Base):
    """One page (or text unit) of extracted research content."""

    __tablename__ = "research_document_pages"
    __table_args__ = (UniqueConstraint("document_id", "page_number", name="uq_research_page"),)

    page_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("research_documents.document_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    document = relationship("ResearchDocument", back_populates="pages")


class ResearchGoal(Base):
    """Accepted / tracked research agenda item for a security."""

    __tablename__ = "research_goals"

    goal_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    security_id: Mapped[str] = mapped_column(
        ForeignKey("securities.security_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="accepted")
    source_cache_id: Mapped[int | None] = mapped_column(
        ForeignKey("research_answer_cache.cache_id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by_user: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ResearchAnswerCache(Base):
    """Cached analyst brief / ask responses (not full prompts by default)."""

    __tablename__ = "research_answer_cache"

    cache_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    security_id: Mapped[str | None] = mapped_column(
        ForeignKey("securities.security_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    request_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    response_json: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False
    )
    citation_page_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    token_in: Mapped[int | None] = mapped_column(Integer)
    token_out: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResearchQueryAudit(Base):
    """Minimal token/latency audit for research LLM calls."""

    __tablename__ = "research_query_audit"

    audit_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    request_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    security_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    cache_hit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    token_in: Mapped[int | None] = mapped_column(Integer)
    token_out: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
