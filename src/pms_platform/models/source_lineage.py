"""Source file lineage and staged import models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pms_platform.db.base import Base

IMPORT_RUN_STATUSES = frozenset(
    {
        "staged",
        "validated",
        "pending_approval",
        "approved",
        "applied",
        "rejected",
        "failed",
    }
)


class SourceFile(Base):
    """Logical source identity (category + display name)."""

    __tablename__ = "source_files"

    source_file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    active_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    versions: Mapped[list[SourceFileVersion]] = relationship(back_populates="source_file")


class SourceFileVersion(Base):
    __tablename__ = "source_file_versions"
    __table_args__ = (
        UniqueConstraint("checksum_sha256", "category", name="uq_source_version_checksum_category"),
    )

    source_file_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_files.source_file_id"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(128))
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"))
    supersedes_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    parse_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    source_file: Mapped[SourceFile] = relationship(back_populates="versions")
    import_runs: Mapped[list[ImportRun]] = relationship(back_populates="source_file_version")


class ImportRun(Base):
    __tablename__ = "import_runs"
    __table_args__ = (
        UniqueConstraint("category", "checksum_sha256", name="uq_import_run_category_checksum"),
    )

    import_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_file_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_file_versions.source_file_version_id"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="staged")
    change_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("change_requests.change_request_id")
    )
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"))
    row_counts: Mapped[dict | None] = mapped_column(JSON)
    validation_summary: Mapped[dict | None] = mapped_column(JSON)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    source_file_version: Mapped[SourceFileVersion] = relationship(back_populates="import_runs")
    issues: Mapped[list[ImportIssue]] = relationship(
        back_populates="import_run", cascade="all, delete-orphan"
    )


class ImportIssue(Base):
    __tablename__ = "import_issues"

    import_issue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    import_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("import_runs.import_run_id"), nullable=False
    )
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[dict | None] = mapped_column(JSON)

    import_run: Mapped[ImportRun] = relationship(back_populates="issues")
