"""Full-text research search (Postgres FTS; SQLite/test fallback)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import Select, func, or_, select, text
from sqlalchemy.orm import Session

from pms_platform.models.research_document import ResearchDocument, ResearchDocumentPage


@dataclass(frozen=True)
class SearchHit:
    page_id: int
    document_id: int
    relative_path: str
    page_number: int
    title: str | None
    security_id: str | None
    snippet: str
    rank: float


def _snippet(text_value: str, query: str, *, max_chars: int) -> str:
    lowered = text_value.lower()
    needle = query.strip().lower().split()[0] if query.strip() else ""
    if needle and needle in lowered:
        idx = lowered.index(needle)
        start = max(0, idx - max_chars // 4)
        end = min(len(text_value), start + max_chars)
        chunk = text_value[start:end].strip()
        prefix = "…" if start > 0 else ""
        suffix = "…" if end < len(text_value) else ""
        return f"{prefix}{chunk}{suffix}"
    return text_value[:max_chars].strip() + ("…" if len(text_value) > max_chars else "")


def search_research_pages(
    session: Session,
    query: str,
    *,
    security_id: str | None = None,
    limit: int = 20,
    snippet_chars: int = 400,
    as_of: date | None = None,
) -> list[SearchHit]:
    """Rank pages by relevance. Empty query returns []."""
    q = (query or "").strip()
    if not q:
        return []

    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        return _search_postgres(
            session,
            q,
            security_id=security_id,
            limit=limit,
            snippet_chars=snippet_chars,
            as_of=as_of,
        )
    return _search_fallback(
        session,
        q,
        security_id=security_id,
        limit=limit,
        snippet_chars=snippet_chars,
        as_of=as_of,
    )


def _base_filters(
    stmt: Select,
    *,
    security_id: str | None,
    as_of: date | None,
) -> Select:
    stmt = stmt.where(ResearchDocument.parse_status == "ok")
    if security_id:
        stmt = stmt.where(
            or_(
                ResearchDocument.security_id == security_id,
                ResearchDocument.security_id.is_(None),
            )
        )
    if as_of is not None:
        # Prefer mtime when present; unknown mtime excluded from PIT mode (no guessing).
        stmt = stmt.where(
            ResearchDocument.mtime_utc.is_not(None),
            func.date(ResearchDocument.mtime_utc) <= as_of,
        )
    return stmt


def _search_postgres(
    session: Session,
    query: str,
    *,
    security_id: str | None,
    limit: int,
    snippet_chars: int,
    as_of: date | None,
) -> list[SearchHit]:
    ts_query = func.plainto_tsquery("english", query)
    # tsv column is maintained by Postgres migration; fall back if missing.
    rank = func.ts_rank_cd(text("research_document_pages.tsv"), ts_query)
    stmt = (
        select(
            ResearchDocumentPage.page_id,
            ResearchDocumentPage.document_id,
            ResearchDocument.relative_path,
            ResearchDocumentPage.page_number,
            ResearchDocument.title,
            ResearchDocument.security_id,
            ResearchDocumentPage.text,
            rank.label("rank"),
        )
        .join(ResearchDocument, ResearchDocument.document_id == ResearchDocumentPage.document_id)
        .where(text("research_document_pages.tsv @@ plainto_tsquery('english', :q)"))
        .params(q=query)
    )
    stmt = _base_filters(stmt, security_id=security_id, as_of=as_of)
    stmt = stmt.order_by(text("rank DESC"), ResearchDocumentPage.page_id).limit(limit)
    try:
        rows = session.execute(stmt).all()
    except Exception:  # noqa: BLE001 — tsv may be absent on fresh sqlite-like setups
        return _search_fallback(
            session,
            query,
            security_id=security_id,
            limit=limit,
            snippet_chars=snippet_chars,
            as_of=as_of,
        )
    return [
        SearchHit(
            page_id=row.page_id,
            document_id=row.document_id,
            relative_path=row.relative_path,
            page_number=row.page_number,
            title=row.title,
            security_id=row.security_id,
            snippet=_snippet(row.text, query, max_chars=snippet_chars),
            rank=float(row.rank or 0.0),
        )
        for row in rows
    ]


def _search_fallback(
    session: Session,
    query: str,
    *,
    security_id: str | None,
    limit: int,
    snippet_chars: int,
    as_of: date | None,
) -> list[SearchHit]:
    tokens = [t for t in query.lower().split() if len(t) >= 2]
    stmt = select(
        ResearchDocumentPage.page_id,
        ResearchDocumentPage.document_id,
        ResearchDocument.relative_path,
        ResearchDocumentPage.page_number,
        ResearchDocument.title,
        ResearchDocument.security_id,
        ResearchDocumentPage.text,
    ).join(ResearchDocument, ResearchDocument.document_id == ResearchDocumentPage.document_id)
    stmt = _base_filters(stmt, security_id=security_id, as_of=as_of)
    if tokens:
        stmt = stmt.where(or_(*[ResearchDocumentPage.text.ilike(f"%{token}%") for token in tokens]))
    stmt = stmt.limit(max(limit * 10, 100))
    rows = session.execute(stmt).all()
    scored: list[SearchHit] = []
    for row in rows:
        lowered = row.text.lower()
        score = sum(lowered.count(token) for token in tokens) if tokens else 1.0
        if security_id and row.security_id == security_id:
            score += 5
        if score <= 0:
            continue
        scored.append(
            SearchHit(
                page_id=row.page_id,
                document_id=row.document_id,
                relative_path=row.relative_path,
                page_number=row.page_number,
                title=row.title,
                security_id=row.security_id,
                snippet=_snippet(row.text, query, max_chars=snippet_chars),
                rank=float(score),
            )
        )
    scored.sort(key=lambda hit: (-hit.rank, hit.page_id))
    return scored[:limit]
