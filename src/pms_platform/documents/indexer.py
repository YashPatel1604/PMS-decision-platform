"""Idempotent research corpus indexer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from pms_platform.documents.extract import extract_file, file_content_hash, file_mtime_utc
from pms_platform.documents.scan import CorpusFile, iter_corpus_files, resolve_corpus_root
from pms_platform.models.research_document import ResearchDocument, ResearchDocumentPage
from pms_platform.models.security import Security


@dataclass(frozen=True)
class IndexResult:
    root: str | None
    scanned: int
    inserted: int
    updated: int
    unchanged: int
    skipped: int
    errors: int
    removed: int


def _guess_security_id(session: Session, relative_path: str, title: str | None) -> str | None:
    """Best-effort link by portfolio_name / symbol tokens in path — never invents numbers."""
    haystack = f"{relative_path} {title or ''}".upper()
    securities = session.scalars(select(Security)).all()
    best: tuple[int, str] | None = None
    for security in securities:
        tokens = [
            t
            for t in (
                security.portfolio_name,
                security.canonical_name,
                security.current_nse_symbol,
                security.bse_code,
                security.isin,
            )
            if t and len(str(t).strip()) >= 3
        ]
        for token in tokens:
            needle = str(token).upper()
            if needle in haystack:
                score = len(needle)
                if best is None or score > best[0]:
                    best = (score, security.security_id)
    return best[1] if best else None


def _upsert_document(session: Session, item: CorpusFile) -> str:
    """Insert or update one file. Returns action: inserted|updated|unchanged|skipped|error."""
    content_hash = file_content_hash(item.absolute_path)
    existing = session.scalar(
        select(ResearchDocument).where(
            ResearchDocument.source_root == item.source_root,
            ResearchDocument.relative_path == item.relative_path,
        )
    )
    if existing is not None and existing.content_hash == content_hash:
        return "unchanged"

    extraction = extract_file(item.absolute_path)
    mtime = file_mtime_utc(item.absolute_path)
    byte_size = item.absolute_path.stat().st_size
    security_id = _guess_security_id(session, item.relative_path, extraction.title)

    if existing is None:
        doc = ResearchDocument(
            relative_path=item.relative_path,
            content_hash=content_hash,
            source_root=item.source_root,
            mime_type=extraction.mime_type,
            byte_size=byte_size,
            mtime_utc=mtime,
            title=extraction.title,
            parse_status=extraction.parse_status,
            parse_error=extraction.parse_error,
            security_id=security_id,
        )
        session.add(doc)
        session.flush()
        action = "inserted"
    else:
        doc = existing
        doc.content_hash = content_hash
        doc.mime_type = extraction.mime_type
        doc.byte_size = byte_size
        doc.mtime_utc = mtime
        doc.title = extraction.title
        doc.parse_status = extraction.parse_status
        doc.parse_error = extraction.parse_error
        doc.security_id = security_id
        session.execute(
            delete(ResearchDocumentPage).where(ResearchDocumentPage.document_id == doc.document_id)
        )
        action = "updated"

    for page in extraction.pages:
        session.add(
            ResearchDocumentPage(
                document_id=doc.document_id,
                page_number=page.page_number,
                text=page.text,
            )
        )

    if extraction.parse_status == "error":
        return "error"
    if extraction.parse_status == "skipped":
        return "skipped"
    return action


def index_research_corpus(
    session: Session,
    *,
    root: Path | None = None,
    prune_missing: bool = True,
) -> IndexResult:
    """Scan Research, upsert by content hash, optionally prune deleted paths."""
    base = resolve_corpus_root(root)
    files = iter_corpus_files(base)
    counts = {
        "inserted": 0,
        "updated": 0,
        "unchanged": 0,
        "skipped": 0,
        "errors": 0,
    }
    seen_paths: set[str] = set()
    for item in files:
        seen_paths.add(item.relative_path)
        action = _upsert_document(session, item)
        if action in counts:
            counts[action] += 1
        session.flush()

    removed = 0
    if prune_missing and base is not None:
        existing_docs = session.scalars(
            select(ResearchDocument).where(ResearchDocument.source_root == "research")
        ).all()
        for doc in existing_docs:
            if doc.relative_path not in seen_paths:
                session.delete(doc)
                removed += 1

    session.commit()
    return IndexResult(
        root=str(base) if base else None,
        scanned=len(files),
        inserted=counts["inserted"],
        updated=counts["updated"],
        unchanged=counts["unchanged"],
        skipped=counts["skipped"],
        errors=counts["errors"],
        removed=removed,
    )


def index_status(session: Session) -> dict[str, object]:
    """Return aggregate index health for API/CLI."""
    total = session.scalar(select(func.count()).select_from(ResearchDocument)) or 0
    pages = session.scalar(select(func.count()).select_from(ResearchDocumentPage)) or 0
    by_status_rows = session.execute(
        select(ResearchDocument.parse_status, func.count()).group_by(ResearchDocument.parse_status)
    ).all()
    last = session.scalar(select(func.max(ResearchDocument.indexed_at)))
    return {
        "document_count": total,
        "page_count": pages,
        "by_parse_status": {status: count for status, count in by_status_rows},
        "last_indexed_at": last.isoformat() if last else None,
        "research_root": str(resolve_corpus_root()) if resolve_corpus_root() else None,
    }
