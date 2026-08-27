"""Staged file import: validate, preview, approve, apply with checksum idempotency."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from pms_platform.config import settings
from pms_platform.ingestion.upload_pipeline import (
    UPLOAD_KINDS,
    UploadIssue,
    commit_workbook_import,
    validate_workbook_import,
)
from pms_platform.models.source_lineage import ImportIssue, ImportRun, SourceFile, SourceFileVersion
from pms_platform.storage.adapter import StorageAdapter, sha256_hex

STAGED_CATEGORIES = UPLOAD_KINDS


@dataclass(frozen=True)
class StageImportResult:
    import_run_id: uuid.UUID
    checksum_sha256: str
    status: str
    deduplicated: bool
    row_counts: dict[str, int]
    error_count: int
    warning_count: int


class StagedImportError(Exception):
    """Business rule violation in staged import pipeline."""


def find_canonical_run(
    session: Session, *, category: str, checksum: str
) -> ImportRun | None:
    return session.scalar(
        select(ImportRun)
        .where(
            ImportRun.category == category,
            ImportRun.checksum_sha256 == checksum,
        )
        .order_by(ImportRun.created_at.desc())
        .limit(1)
    )


def stage_import_bytes(
    session: Session,
    *,
    category: str,
    filename: str,
    data: bytes,
    uploaded_by: int | None,
    storage: StorageAdapter,
    mime_type: str | None = None,
) -> StageImportResult:
    """Store file and create or return existing import run (checksum idempotent)."""
    if category not in STAGED_CATEGORIES:
        raise StagedImportError(f"unsupported category: {category}")

    checksum = sha256_hex(data)
    existing = find_canonical_run(session, category=category, checksum=checksum)
    if existing is not None:
        return StageImportResult(
            import_run_id=existing.import_run_id,
            checksum_sha256=checksum,
            status=existing.status,
            deduplicated=True,
            row_counts=dict(existing.row_counts or {}),
            error_count=sum(1 for i in existing.issues if i.severity == "error"),
            warning_count=sum(1 for i in existing.issues if i.severity == "warning"),
        )

    source = SourceFile(category=category, display_name=filename)
    session.add(source)
    session.flush()

    storage_key = f"{category}/{checksum}/{filename}"
    storage.put(storage_key, data, content_type=mime_type)

    version = SourceFileVersion(
        source_file_id=source.source_file_id,
        category=category,
        storage_key=storage_key,
        original_filename=filename,
        mime_type=mime_type,
        checksum_sha256=checksum,
        byte_size=len(data),
        uploaded_by=uploaded_by,
        parse_status="pending",
    )
    session.add(version)
    session.flush()

    run = ImportRun(
        source_file_version_id=version.source_file_version_id,
        category=category,
        checksum_sha256=checksum,
        status="staged",
        created_by=uploaded_by,
    )
    session.add(run)
    session.flush()

    validate_import_run(session, run.import_run_id, storage=storage)
    session.refresh(run)
    return StageImportResult(
        import_run_id=run.import_run_id,
        checksum_sha256=checksum,
        status=run.status,
        deduplicated=False,
        row_counts=dict(run.row_counts or {}),
        error_count=sum(1 for i in run.issues if i.severity == "error"),
        warning_count=sum(1 for i in run.issues if i.severity == "warning"),
    )


def _materialize_workbook(version: SourceFileVersion, data: bytes) -> Path:
    """Stable on-disk path per checksum so import batches dedupe correctly."""
    name = version.original_filename or "upload.xlsx"
    dest = settings.upload_dir / "staged_lineage" / version.checksum_sha256 / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        dest.write_bytes(data)
    return dest


def _import_issue_from_upload(
    run_id: uuid.UUID, issue: UploadIssue, *, severity: str | None = None
) -> ImportIssue:
    mapped = severity or ("error" if issue.severity == "ERROR" else "warning")
    return ImportIssue(
        import_run_id=run_id,
        severity=mapped,
        code=issue.code,
        message=issue.message,
        context={
            "security_id": issue.security_id,
            "source_key": issue.source_key,
            "event_date": issue.event_date,
        },
    )


def validate_import_run(
    session: Session,
    import_run_id: uuid.UUID,
    *,
    storage: StorageAdapter,
) -> ImportRun:
    run = session.get(ImportRun, import_run_id)
    if run is None:
        raise StagedImportError("import run not found")
    if run.status == "applied":
        return run

    version = run.source_file_version
    data = storage.get(version.storage_key)
    path = _materialize_workbook(version, data)
    issues: list[ImportIssue] = []
    row_counts: dict[str, int] = {"bytes": len(data)}

    if not filename_looks_like_excel(version.original_filename):
        issues.append(
            ImportIssue(
                import_run_id=run.import_run_id,
                severity="error",
                code="bad_extension",
                message="Expected .xlsx or .xls upload",
            )
        )
    elif run.category not in STAGED_CATEGORIES:
        issues.append(
            ImportIssue(
                import_run_id=run.import_run_id,
                severity="error",
                code="unsupported_category",
                message=f"unsupported category: {run.category}",
            )
        )
    else:
        try:
            upload_issues, counts = validate_workbook_import(
                session, kind=run.category, path=path
            )
            row_counts.update(counts)
            issues.extend(
                _import_issue_from_upload(run.import_run_id, issue) for issue in upload_issues
            )
        except Exception as exc:  # noqa: BLE001 — surface parse failure to user
            issues.append(
                ImportIssue(
                    import_run_id=run.import_run_id,
                    severity="error",
                    code="validate_failed",
                    message=str(exc),
                )
            )

    session.execute(delete(ImportIssue).where(ImportIssue.import_run_id == run.import_run_id))
    for issue in issues:
        session.add(issue)

    run.row_counts = row_counts
    run.validation_summary = {
        "error_count": sum(1 for i in issues if i.severity == "error"),
        "warning_count": sum(1 for i in issues if i.severity == "warning"),
    }
    has_errors = any(i.severity == "error" for i in issues)
    run.status = "failed" if has_errors else "validated"
    version.parse_status = "failed" if has_errors else "validated"
    session.flush()
    return run


def preview_import_run(session: Session, import_run_id: uuid.UUID) -> dict[str, Any]:
    run = session.get(ImportRun, import_run_id)
    if run is None:
        raise StagedImportError("import run not found")
    return serialize_import_run(run)


def apply_import_run(
    session: Session,
    import_run_id: uuid.UUID,
    *,
    storage: StorageAdapter | None = None,
) -> ImportRun:
    """Apply a validated import run into Postgres (idempotent)."""
    run = session.get(ImportRun, import_run_id)
    if run is None:
        raise StagedImportError("import run not found")
    if run.status == "applied":
        return run
    if run.status not in ("validated", "approved", "pending_approval"):
        raise StagedImportError(f"cannot apply from status {run.status}")

    version = run.source_file_version
    if version is None:
        raise StagedImportError("source file version missing")
    source = session.get(SourceFile, version.source_file_id)
    if source is None:
        raise StagedImportError("source file missing")

    if storage is None:
        from pms_platform.storage import get_storage

        storage = get_storage()

    data = storage.get(version.storage_key)
    path = _materialize_workbook(version, data)
    try:
        row_counts, episode_summary = commit_workbook_import(
            session, kind=run.category, path=path
        )
    except Exception as exc:
        raise StagedImportError(str(exc)) from exc

    run.status = "applied"
    run.applied_at = datetime.now(UTC)
    run.row_counts = row_counts
    run.validation_summary = {
        **(run.validation_summary or {}),
        "applied": True,
        "episode_summary": episode_summary,
    }
    source.active_version_id = run.source_file_version_id
    version.parse_status = "applied"
    session.flush()
    return run


def can_preview_import(
    run: ImportRun,
    *,
    viewer_user_id: int,
    can_view_all: bool,
) -> bool:
    if can_view_all:
        return True
    if run.created_by == viewer_user_id:
        return True
    return run.status == "applied"


def serialize_import_run(run: ImportRun) -> dict[str, Any]:
    version = run.source_file_version
    return {
        "import_run_id": str(run.import_run_id),
        "category": run.category,
        "checksum_sha256": run.checksum_sha256,
        "status": run.status,
        "original_filename": version.original_filename,
        "byte_size": version.byte_size,
        "row_counts": run.row_counts,
        "validation_summary": run.validation_summary,
        "change_request_id": str(run.change_request_id) if run.change_request_id else None,
        "applied_at": run.applied_at.isoformat() if run.applied_at else None,
        "issues": [
            {
                "severity": i.severity,
                "code": i.code,
                "message": i.message,
                "context": i.context,
            }
            for i in run.issues
        ],
    }


def filename_looks_like_excel(name: str) -> bool:
    lower = name.lower()
    return lower.endswith(".xlsx") or lower.endswith(".xls")
