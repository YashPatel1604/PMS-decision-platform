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
from pms_platform.intelligence.theses import get_approved_thesis
from pms_platform.documents.prompts import assemble_ask_messages, assemble_brief_messages
from pms_platform.documents.search import SearchHit, list_linked_pages, search_research_pages
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
    security_id: str | None = None


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
    scope: str = "",
) -> str:
    payload = "|".join(
        [
            kind,
            security_id or "",
            _normalize_question(question),
            ",".join(str(i) for i in sorted(chunk_ids)),
            model,
            prompt_version,
            scope,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _ground_citations(payload: dict[str, Any], chunk_ids: list[int]) -> dict[str, Any]:
    """Keep only citations whose page_id was actually retrieved."""
    allowed = set(chunk_ids)
    out = dict(payload)
    grounded: list[dict[str, Any]] = []
    for item in out.get("citations") or []:
        if not isinstance(item, dict) or item.get("page_id") is None:
            continue
        try:
            page_id = int(item["page_id"])
        except (TypeError, ValueError):
            continue
        if page_id in allowed:
            grounded.append(item)
    out["citations"] = grounded
    if not isinstance(out.get("insufficient_evidence"), list):
        out["insufficient_evidence"] = []
    return out


def _parse_json_content(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise json.JSONDecodeError("Expected JSON object", text, 0)
    return parsed


def _validate_brief_schema(payload: dict[str, Any], *, chunk_ids: list[int]) -> dict[str, Any]:
    """Ensure required brief keys exist; drop citations that are not in retrieved pages."""
    out = dict(payload)
    out.setdefault("security_query", "")
    thesis = out.get("thesis_map")
    if not isinstance(thesis, dict):
        thesis = {}
    out["thesis_map"] = {
        "beliefs": list(thesis.get("beliefs") or []),
        "must_stay_true": list(thesis.get("must_stay_true") or []),
        "falsifiers": list(thesis.get("falsifiers") or []),
    }
    agenda = out.get("research_agenda")
    out["research_agenda"] = agenda if isinstance(agenda, list) else []
    gaps = out.get("evidence_gaps")
    out["evidence_gaps"] = gaps if isinstance(gaps, list) else []
    checklist = out.get("monitoring_checklist")
    out["monitoring_checklist"] = checklist if isinstance(checklist, list) else []
    scenarios = out.get("scenarios")
    if not isinstance(scenarios, dict):
        scenarios = {}
    cleaned_scenarios: dict[str, Any] = {}
    for key in ("bull", "base", "bear"):
        row = scenarios.get(key)
        if not isinstance(row, dict):
            row = {}
        cleaned_scenarios[key] = {
            "summary": str(row.get("summary") or "Insufficient evidence"),
            "citations": list(row.get("citations") or []),
        }
    out["scenarios"] = cleaned_scenarios
    insuff = out.get("insufficient_evidence")
    out["insufficient_evidence"] = insuff if isinstance(insuff, list) else []

    allowed = set(chunk_ids)
    citations = out.get("citations")
    if not isinstance(citations, list):
        citations = []
    grounded: list[dict[str, Any]] = []
    for item in citations:
        if not isinstance(item, dict):
            continue
        doc_id = item.get("document_id")
        page = item.get("page")
        page_id = item.get("page_id")
        if page_id is not None:
            try:
                pid = int(page_id)
            except (TypeError, ValueError):
                continue
            if pid not in allowed:
                continue
            grounded.append(item)
            continue
        # path:page citations stay; document_id alone is not enough without page_id.
        if item.get("relative_path") is not None and page is not None:
            grounded.append(item)
            continue
        if doc_id is not None and page is not None:
            grounded.append(item)
    out["citations"] = grounded
    out["retrieved_page_ids"] = list(chunk_ids)
    return out


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


def _note_names(hits: list[SearchHit]) -> str:
    names: list[str] = []
    for hit in hits:
        name = (hit.title or hit.relative_path or "").strip()
        if name and name not in names:
            names.append(name)
    if not names:
        return "the selected company"
    shown = ", ".join(names[:4])
    extra = len(names) - 4
    return f"{shown} and {extra} more" if extra > 0 else shown


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
    linked_only: bool = False,
) -> list[SearchHit]:
    return search_research_pages(
        session,
        query,
        security_id=security_id,
        limit=settings.research_rag_max_chunks * 3,
        snippet_chars=settings.research_rag_snippet_chars,
        as_of=as_of,
        linked_only=linked_only,
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


def list_saved_briefs(session: Session, *, limit: int = 40) -> list[dict[str, Any]]:
    """Finished briefs, newest first. A failed reply is not included."""
    from pms_platform.models.security import Security

    rows = session.execute(
        select(ResearchAnswerCache, Security.portfolio_name)
        .outerjoin(Security, Security.security_id == ResearchAnswerCache.security_id)
        .where(ResearchAnswerCache.request_kind == "brief")
        .order_by(ResearchAnswerCache.created_at.desc())
        .limit(max(limit * 2, limit))
    ).all()
    items: list[dict[str, Any]] = []
    for row, company in rows:
        body = row.response_json if isinstance(row.response_json, dict) else {}
        if body.get("brief_error"):
            continue
        thesis = body.get("thesis_map") if isinstance(body.get("thesis_map"), dict) else {}
        beliefs = thesis.get("beliefs") if isinstance(thesis, dict) else None
        summary = ""
        if isinstance(beliefs, list) and beliefs and isinstance(beliefs[0], str):
            summary = beliefs[0]
        elif isinstance(body.get("security_query"), str):
            summary = body["security_query"]
        items.append(
            {
                "cache_id": row.cache_id,
                "security_id": row.security_id,
                "company": company or body.get("security_query") or "Unknown company",
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "token_in": row.token_in,
                "token_out": row.token_out,
                "summary": summary,
            }
        )
        if len(items) >= limit:
            break
    return items


def get_saved_brief(session: Session, cache_id: int) -> AnalystResult | None:
    row = session.get(ResearchAnswerCache, cache_id)
    if row is None or row.request_kind != "brief":
        return None
    body = row.response_json if isinstance(row.response_json, dict) else {}
    if body.get("brief_error"):
        return None
    return AnalystResult(
        kind="brief",
        response=dict(body),
        cache_hit=True,
        cache_id=row.cache_id,
        model=row.model,
        token_in=row.token_in,
        token_out=row.token_out,
        chunk_ids=list(row.citation_page_ids or []),
        called_llm=False,
        security_id=row.security_id,
    )


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


def brief_output_cap(sent_tokens: int) -> int:
    """Reply room follows the notes. Short notes do not get a long cap."""
    return max(2000, min(settings.research_brief_max_output_tokens, sent_tokens))


def _linked_note_size(session: Session, security_id: str) -> tuple[int, list[str]]:
    from sqlalchemy import func

    from pms_platform.models.research_document import ResearchDocument, ResearchDocumentPage

    chars = session.scalar(
        select(func.coalesce(func.sum(func.length(ResearchDocumentPage.text)), 0))
        .join(ResearchDocument, ResearchDocument.document_id == ResearchDocumentPage.document_id)
        .where(
            ResearchDocument.security_id == security_id,
            ResearchDocument.parse_status == "ok",
        )
    )
    titles = session.scalars(
        select(ResearchDocument.title)
        .where(
            ResearchDocument.security_id == security_id,
            ResearchDocument.parse_status == "ok",
        )
        .order_by(ResearchDocument.document_id.desc())
    ).all()
    names = [title.strip() for title in titles if title and title.strip()]
    return max(0, int(chars or 0) // 4), names


def preview_research_brief(
    session: Session,
    *,
    security_id: str | None = None,
    query_name: str | None = None,
    extra_question: str | None = None,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Token size of a brief before any model call."""
    label, _facts, hits = _brief_inputs(
        session,
        security_id=security_id,
        query_name=query_name,
        extra_question=extra_question,
        as_of=as_of,
    )
    note_tokens = 0
    note_names: list[str] = []
    if security_id:
        note_tokens, note_names = _linked_note_size(session, security_id)
    if not hits:
        return {
            "approx_tokens": note_tokens,
            "sent_tokens": 0,
            "page_count": 0,
            "notes": note_names,
            "warn": note_tokens >= settings.research_brief_warn_tokens,
            "output_cap": 0,
            "company": label,
        }
    assembled = assemble_brief_messages(
        security_label=label,
        facts=_facts,
        hits=hits,
        extra_question=extra_question,
    )
    sent = assembled.approx_tokens
    return {
        "approx_tokens": max(note_tokens, sent),
        "sent_tokens": sent,
        "page_count": len(assembled.chunk_ids),
        "notes": note_names or _note_names(hits).split(", "),
        "warn": max(note_tokens, sent) >= settings.research_brief_warn_tokens,
        "output_cap": brief_output_cap(sent),
        "company": label,
    }


def _brief_inputs(
    session: Session,
    *,
    security_id: str | None,
    query_name: str | None,
    extra_question: str | None,
    as_of: date | None,
) -> tuple[str, dict[str, Any], list[SearchHit]]:
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
                query_name or "",
                str(facts.get("nse_symbol") or ""),
                extra_question or "",
            )
            if part
        ).strip()
        or label
    )
    linked = bool(security_id)
    hits = _retrieve(
        session, query=search_q, security_id=security_id, as_of=as_of, linked_only=linked
    )
    if not hits and security_id:
        hits = search_research_pages(
            session,
            label,
            security_id=security_id,
            limit=settings.research_rag_max_chunks * 3,
            snippet_chars=settings.research_rag_snippet_chars,
            as_of=as_of,
            linked_only=True,
        )
    if not hits and security_id:
        hits = list_linked_pages(
            session,
            security_id,
            limit=settings.research_rag_max_chunks,
            snippet_chars=settings.research_rag_snippet_chars,
        )
    return label, facts, hits


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
    label, facts, hits = _brief_inputs(
        session,
        security_id=security_id,
        query_name=query_name,
        extra_question=extra_question,
        as_of=as_of,
    )
    approved = get_approved_thesis(session, security_id) if security_id else None
    scope = f"linked:{approved.version if approved else 0}" if security_id else "open"

    if not hits:
        response = _insufficient_brief(
            label,
            f"No notes are linked to {label}. Upload the file again with this company selected. "
            "A file uploaded without a company is not used.",
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
        scope=scope,
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

    output_cap = brief_output_cap(assembled.approx_tokens)
    result = chat_completion(
        assembled.messages,
        client=http_client,
        max_tokens=output_cap,
    )
    parsed_ok = True
    try:
        response = _ground_citations(
            _validate_brief_schema(
                _parse_json_content(result.content),
                chunk_ids=assembled.chunk_ids,
            ),
            assembled.chunk_ids,
        )
    except json.JSONDecodeError:
        parsed_ok = False
        notes = _note_names(hits)
        cut_off = result.finish_reason == "length" or (
            result.token_out is not None
            and result.token_out >= output_cap
        )
        if cut_off:
            reason = (
                f"The reply was cut off after {result.token_out or output_cap} tokens, "
                f"before it finished. These notes were included: {notes}. Nothing from this attempt was saved."
            )
        else:
            reason = (
                f"The reply could not be read. These notes were included: {notes}. "
                "Nothing from this attempt was saved."
            )
        response = _insufficient_brief(label, reason)
        response["brief_error"] = reason

    row = None
    if parsed_ok:
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
        error=None if parsed_ok else "brief reply was not usable",
    )
    session.commit()
    return AnalystResult(
        kind="brief",
        response=response,
        cache_hit=False,
        cache_id=row.cache_id if row is not None else None,
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
    approved = get_approved_thesis(session, security_id) if security_id else None
    scope = f"linked:{approved.version if approved else 0}" if security_id else "open"
    hits = search_research_pages(
        session,
        q if not label else f"{label} {q}",
        security_id=security_id,
        limit=settings.research_ask_max_chunks * 3,
        snippet_chars=settings.research_rag_snippet_chars,
        as_of=as_of,
        linked_only=bool(security_id),
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

    assembled = assemble_ask_messages(
        question=q,
        facts=facts,
        hits=hits,
        max_chunks=settings.research_ask_max_chunks,
        max_context_tokens=settings.research_ask_max_context_tokens,
    )
    key = _cache_key(
        kind="ask",
        security_id=security_id,
        question=q,
        chunk_ids=assembled.chunk_ids,
        model=settings.xai_model,
        prompt_version=settings.research_analyst_prompt_version,
        scope=scope,
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

    result = chat_completion(
        assembled.messages,
        client=http_client,
        max_tokens=settings.research_ask_max_output_tokens,
    )
    try:
        response = _ground_citations(_parse_json_content(result.content), assembled.chunk_ids)
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
