"""Orchestrate research brief / ask with cache and egress guards."""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.config import settings
from pms_platform.documents.facts import collect_security_facts
from pms_platform.documents.prompts import assemble_ask_messages, assemble_brief_messages
from pms_platform.documents.search import SearchHit, search_research_pages
from pms_platform.documents.xai_client import XaiConfigError, chat_completion, xai_configured
from pms_platform.models.research_document import (
    ResearchAnswerCache,
    ResearchQueryAudit,
)
from pms_platform.models.security import Security


@dataclass(frozen=True)
class AnalystResult:
    kind: str
    response: dict[str, Any]
    cache_hit: bool
    cache_id: int | None
    model: str | None
    token_in: int | None
    token_out: int | None
    chunk_ids: list[int]
    called_llm: bool


def _normalize_question(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _cache_key(
    *,
    kind: str,
    security_id: str | None,
    question: str,
    chunk_ids: list[int],
    model: str,
    prompt_version: str,
) -> str:
    payload = "|".join(
        [
            kind,
            security_id or "",
            _normalize_question(question),
            ",".join(str(i) for i in sorted(chunk_ids)),
            model,
            prompt_version,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parse_json_content(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise json.JSONDecodeError("Expected JSON object", text, 0)
    return parsed


def _insufficient_brief(security_label: str, reason: str) -> dict[str, Any]:
    return {
        "security_query": security_label,
        "thesis_map": {"beliefs": [], "must_stay_true": [], "falsifiers": []},
        "research_agenda": [
            {
                "title": "Index or locate primary research documents for this name",
                "rationale": reason,
                "priority": 1,
                "suggested_sources": ["notes", "filing"],
            }
        ],
        "evidence_gaps": [reason],
        "monitoring_checklist": [],
        "scenarios": {
            "bull": {"summary": "Insufficient evidence", "citations": []},
            "base": {"summary": "Insufficient evidence", "citations": []},
            "bear": {"summary": "Insufficient evidence", "citations": []},
        },
        "insufficient_evidence": [reason],
        "citations": [],
    }


def _security_label(session: Session, security_id: str | None, fallback: str | None) -> str:
    if security_id:
        security = session.get(Security, security_id)
        if security:
            return security.portfolio_name
    return fallback or security_id or "unknown"


def _retrieve(
    session: Session,
    *,
    query: str,
    security_id: str | None,
    as_of: date | None,
) -> list[SearchHit]:
    return search_research_pages(
        session,
        query,
        security_id=security_id,
        limit=settings.research_rag_max_chunks * 3,
        snippet_chars=settings.research_rag_snippet_chars,
        as_of=as_of,
    )


def _get_fresh_cache(session: Session, key: str) -> ResearchAnswerCache | None:
    row = session.scalar(select(ResearchAnswerCache).where(ResearchAnswerCache.cache_key == key))
    if row is None:
        return None
    if row.expires_at is not None:
        expires = row.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if expires < datetime.now(tz=UTC):
            return None
    return row


def _store_cache(
    session: Session,
    *,
    key: str,
    kind: str,
    security_id: str | None,
    response: dict[str, Any],
    chunk_ids: list[int],
    model: str,
    token_in: int | None,
    token_out: int | None,
) -> ResearchAnswerCache:
    expires = datetime.now(tz=UTC) + timedelta(days=settings.research_answer_cache_ttl_days)
    row = ResearchAnswerCache(
        cache_key=key,
        security_id=security_id,
        request_kind=kind,
        response_json=response,
        citation_page_ids=chunk_ids,
        model=model,
        prompt_version=settings.research_analyst_prompt_version,
        token_in=token_in,
        token_out=token_out,
        expires_at=expires,
    )
    session.add(row)
    session.flush()
    return row


def _audit(
    session: Session,
    *,
    kind: str,
    security_id: str | None,
    cache_hit: bool,
    token_in: int | None,
    token_out: int | None,
    latency_ms: int | None,
    error: str | None = None,
) -> None:
    session.add(
        ResearchQueryAudit(
            request_kind=kind,
            security_id=security_id,
            cache_hit=cache_hit,
            token_in=token_in,
            token_out=token_out,
            latency_ms=latency_ms,
            error=error,
        )
    )


def generate_research_brief(
    session: Session,
    *,
    security_id: str | None = None,
    query_name: str | None = None,
    extra_question: str | None = None,
    as_of: date | None = None,
    force_refresh: bool = False,
    http_client: Any | None = None,
) -> AnalystResult:
    """Produce citation-backed research brief; skip LLM when no snippets."""
    started = time.perf_counter()
    label = _security_label(session, security_id, query_name)
    facts = (
        collect_security_facts(session, security_id, as_of=as_of)
        if security_id
        else {"found": False, "security_query": label}
    )
    search_q = (
        " ".join(
            part
            for part in (
                label,
                str(facts.get("nse_symbol") or ""),
                extra_question or "",
            )
            if part
        ).strip()
        or label
    )
    hits = _retrieve(session, query=search_q, security_id=security_id, as_of=as_of)
    # If name-only retrieval is empty, broaden to any pages linked to the security.
    if not hits and security_id:
        hits = search_research_pages(
            session,
            label,
            security_id=security_id,
            limit=settings.research_rag_max_chunks * 3,
            snippet_chars=settings.research_rag_snippet_chars,
            as_of=as_of,
        )
    if not hits and security_id:
        from sqlalchemy import select

        from pms_platform.models.research_document import ResearchDocument, ResearchDocumentPage

        rows = session.execute(
            select(
                ResearchDocumentPage.page_id,
                ResearchDocumentPage.document_id,
                ResearchDocument.relative_path,
                ResearchDocumentPage.page_number,
                ResearchDocument.title,
                ResearchDocument.security_id,
                ResearchDocumentPage.text,
            )
            .join(ResearchDocument)
            .where(
                ResearchDocument.security_id == security_id,
                ResearchDocument.parse_status == "ok",
            )
            .limit(settings.research_rag_max_chunks)
        ).all()
        hits = [
            SearchHit(
                page_id=row.page_id,
                document_id=row.document_id,
                relative_path=row.relative_path,
                page_number=row.page_number,
                title=row.title,
                security_id=row.security_id,
                snippet=row.text[: settings.research_rag_snippet_chars],
                rank=1.0,
            )
            for row in rows
        ]

    if not hits:
        response = _insufficient_brief(
            label,
            "No indexed research snippets matched this security. Run research-index and widen corpus globs if needed.",
        )
        _audit(
            session,
            kind="brief",
            security_id=security_id,
            cache_hit=False,
            token_in=0,
            token_out=0,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
        session.commit()
        return AnalystResult(
            kind="brief",
            response=response,
            cache_hit=False,
            cache_id=None,
            model=None,
            token_in=0,
            token_out=0,
            chunk_ids=[],
            called_llm=False,
        )

    assembled = assemble_brief_messages(
        security_label=label,
        facts=facts,
        hits=hits,
        extra_question=extra_question,
    )
    key = _cache_key(
        kind="brief",
        security_id=security_id,
        question=extra_question or "brief",
        chunk_ids=assembled.chunk_ids,
        model=settings.xai_model,
        prompt_version=settings.research_analyst_prompt_version,
    )
    if not force_refresh:
        cached = _get_fresh_cache(session, key)
        if cached is not None:
            _audit(
                session,
                kind="brief",
                security_id=security_id,
                cache_hit=True,
                token_in=0,
                token_out=0,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
            session.commit()
            return AnalystResult(
                kind="brief",
                response=dict(cached.response_json),
                cache_hit=True,
                cache_id=cached.cache_id,
                model=cached.model,
                token_in=cached.token_in,
                token_out=cached.token_out,
                chunk_ids=list(cached.citation_page_ids or assembled.chunk_ids),
                called_llm=False,
            )

    if not xai_configured():
        _audit(
            session,
            kind="brief",
            security_id=security_id,
            cache_hit=False,
            token_in=None,
            token_out=None,
            latency_ms=int((time.perf_counter() - started) * 1000),
            error="XAI_API_KEY missing",
        )
        session.commit()
        raise XaiConfigError("XAI_API_KEY is not configured")

    result = chat_completion(assembled.messages, client=http_client)
    try:
        response = _parse_json_content(result.content)
    except json.JSONDecodeError:
        response = _insufficient_brief(label, "Model returned non-JSON content")
        response["raw_content_preview"] = result.content[:500]

    row = _store_cache(
        session,
        key=key,
        kind="brief",
        security_id=security_id,
        response=response,
        chunk_ids=assembled.chunk_ids,
        model=result.model,
        token_in=result.token_in,
        token_out=result.token_out,
    )
    _audit(
        session,
        kind="brief",
        security_id=security_id,
        cache_hit=False,
        token_in=result.token_in,
        token_out=result.token_out,
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
    session.commit()
    return AnalystResult(
        kind="brief",
        response=response,
        cache_hit=False,
        cache_id=row.cache_id,
        model=result.model,
        token_in=result.token_in,
        token_out=result.token_out,
        chunk_ids=assembled.chunk_ids,
        called_llm=True,
    )


def generate_research_ask(
    session: Session,
    *,
    question: str,
    security_id: str | None = None,
    as_of: date | None = None,
    force_refresh: bool = False,
    http_client: Any | None = None,
) -> AnalystResult:
    """Secondary Q&A path with the same egress/cache controls."""
    started = time.perf_counter()
    q = question.strip()
    if not q:
        raise ValueError("question is required")

    facts = collect_security_facts(session, security_id, as_of=as_of) if security_id else None
    label = _security_label(session, security_id, None)
    hits = _retrieve(
        session, query=q if not label else f"{label} {q}", security_id=security_id, as_of=as_of
    )

    if not hits:
        response = {
            "answer": "Insufficient evidence — no indexed snippets matched this question.",
            "citations": [],
            "insufficient_evidence": ["No matching research pages in the index."],
        }
        _audit(
            session,
            kind="ask",
            security_id=security_id,
            cache_hit=False,
            token_in=0,
            token_out=0,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
        session.commit()
        return AnalystResult(
            kind="ask",
            response=response,
            cache_hit=False,
            cache_id=None,
            model=None,
            token_in=0,
            token_out=0,
            chunk_ids=[],
            called_llm=False,
        )

    assembled = assemble_ask_messages(question=q, facts=facts, hits=hits)
    key = _cache_key(
        kind="ask",
        security_id=security_id,
        question=q,
        chunk_ids=assembled.chunk_ids,
        model=settings.xai_model,
        prompt_version=settings.research_analyst_prompt_version,
    )
    if not force_refresh:
        cached = _get_fresh_cache(session, key)
        if cached is not None:
            _audit(
                session,
                kind="ask",
                security_id=security_id,
                cache_hit=True,
                token_in=0,
                token_out=0,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
            session.commit()
            return AnalystResult(
                kind="ask",
                response=dict(cached.response_json),
                cache_hit=True,
                cache_id=cached.cache_id,
                model=cached.model,
                token_in=cached.token_in,
                token_out=cached.token_out,
                chunk_ids=list(cached.citation_page_ids or assembled.chunk_ids),
                called_llm=False,
            )

    if not xai_configured():
        _audit(
            session,
            kind="ask",
            security_id=security_id,
            cache_hit=False,
            token_in=None,
            token_out=None,
            latency_ms=int((time.perf_counter() - started) * 1000),
            error="XAI_API_KEY missing",
        )
        session.commit()
        raise XaiConfigError("XAI_API_KEY is not configured")

    result = chat_completion(assembled.messages, client=http_client)
    try:
        response = _parse_json_content(result.content)
    except json.JSONDecodeError:
        response = {
            "answer": result.content.strip(),
            "citations": [],
            "insufficient_evidence": ["Model returned non-JSON; raw answer preserved."],
        }

    row = _store_cache(
        session,
        key=key,
        kind="ask",
        security_id=security_id,
        response=response,
        chunk_ids=assembled.chunk_ids,
        model=result.model,
        token_in=result.token_in,
        token_out=result.token_out,
    )
    _audit(
        session,
        kind="ask",
        security_id=security_id,
        cache_hit=False,
        token_in=result.token_in,
        token_out=result.token_out,
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
    session.commit()
    return AnalystResult(
        kind="ask",
        response=response,
        cache_hit=False,
        cache_id=row.cache_id,
        model=result.model,
        token_in=result.token_in,
        token_out=result.token_out,
        chunk_ids=assembled.chunk_ids,
        called_llm=True,
    )
