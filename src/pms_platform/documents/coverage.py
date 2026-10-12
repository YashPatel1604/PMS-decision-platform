"""Opt-in coverage / delta helpers for research analyst loops."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from pms_platform.documents.analyst import generate_research_brief
from pms_platform.documents.facts import collect_security_facts
from pms_platform.documents.goals import list_goals
from pms_platform.intelligence.theses import get_active_thesis, get_approved_thesis
from pms_platform.models.enums import EpisodeStatus
from pms_platform.models.episode import InvestmentEpisode
from pms_platform.models.investment_thesis import InvestmentThesis
from pms_platform.models.research_document import ResearchAnswerCache, ResearchDocument, ResearchReview
from pms_platform.models.security import Security
from pms_platform.models.watchlist import WatchlistMember


@dataclass(frozen=True)
class CoverageItem:
    security_id: str
    reason: str


@dataclass(frozen=True)
class BookFirm:
    security_id: str
    display_name: str
    source: str  # holding | watchlist | both


def _book_security_id_sets(session: Session) -> tuple[set[str], set[str]]:
    open_ids = set(
        session.scalars(
            select(InvestmentEpisode.security_id).where(
                InvestmentEpisode.status == EpisodeStatus.OPEN.value
            )
        ).all()
    )
    watch_ids = {
        sid
        for sid in session.scalars(
            select(WatchlistMember.security_id).where(WatchlistMember.security_id.is_not(None))
        ).all()
        if sid
    }
    return open_ids, watch_ids


def list_book_firms(session: Session) -> list[BookFirm]:
    """Open holdings + watchlist names that search/brief can target."""
    open_ids, watch_ids = _book_security_id_sets(session)
    all_ids = sorted(open_ids | watch_ids)
    if not all_ids:
        return []
    securities = {
        row.security_id: row
        for row in session.scalars(select(Security).where(Security.security_id.in_(all_ids))).all()
    }
    wl_names: dict[str, str] = {}
    for sid, name in session.execute(
        select(WatchlistMember.security_id, WatchlistMember.display_name).where(
            WatchlistMember.security_id.in_(all_ids)
        )
    ).all():
        if sid and name and sid not in wl_names:
            wl_names[sid] = name
    out: list[BookFirm] = []
    for sid in all_ids:
        sec = securities.get(sid)
        display = (
            (sec.canonical_name or sec.portfolio_name) if sec else None
        ) or wl_names.get(sid) or sid
        if sid in open_ids and sid in watch_ids:
            source = "both"
        elif sid in open_ids:
            source = "holding"
        else:
            source = "watchlist"
        out.append(BookFirm(security_id=sid, display_name=display, source=source))
    out.sort(key=lambda f: f.display_name.casefold())
    return out


def ensure_research_company(
    session: Session,
    name: str,
    *,
    nse_symbol: str | None = None,
    bse_code: str | None = None,
) -> Security:
    """Find a company by name or symbol, or create one so a note can be attached."""
    cleaned = " ".join(name.split()).strip()[:128]
    if len(cleaned) < 2:
        raise ValueError("Type the company name")
    symbol = (nse_symbol or "").strip().upper() or None
    if symbol and symbol.endswith(".NS"):
        symbol = symbol[:-3]
    bse = (bse_code or "").strip() or None
    existing = session.scalar(
        select(Security).where(
            or_(
                func.lower(Security.portfolio_name) == cleaned.lower(),
                func.lower(Security.canonical_name) == cleaned.lower(),
            )
        )
    )
    if existing is None and symbol:
        existing = session.scalar(
            select(Security).where(func.upper(Security.current_nse_symbol) == symbol)
        )
    if existing is not None:
        return existing
    digest = hashlib.sha256(cleaned.lower().encode()).hexdigest().upper()
    sec_id = f"RS{digest[:12]}"
    if session.get(Security, sec_id) is not None:
        sec_id = f"RS{digest[12:26]}"
    sec = Security(
        security_id=sec_id[:16],
        portfolio_name=cleaned,
        canonical_name=cleaned,
        current_nse_symbol=symbol,
        bse_code=bse,
        status="ACTIVE",
        verification_status="RESEARCH",
    )
    session.add(sec)
    session.commit()
    session.refresh(sec)
    return sec


def research_status_by_security(
    session: Session, security_ids: list[str] | set[str]
) -> dict[str, str]:
    """Map security_id → researched | backlog.

    researched = active thesis, cached brief, or linked research document.
    """
    ids = sorted({sid for sid in security_ids if sid})
    if not ids:
        return {}
    researched: set[str] = set()
    for sid in session.scalars(
        select(InvestmentThesis.security_id).where(
            InvestmentThesis.security_id.in_(ids),
            InvestmentThesis.status.in_(("active", "approved")),
        )
    ).all():
        if sid:
            researched.add(sid)
    for sid in session.scalars(
        select(ResearchDocument.security_id).where(
            ResearchDocument.security_id.in_(ids),
            ResearchDocument.parse_status == "ok",
        )
    ).all():
        if sid:
            researched.add(sid)
    for sid in session.scalars(
        select(ResearchAnswerCache.security_id).where(
            ResearchAnswerCache.security_id.in_(ids),
            ResearchAnswerCache.request_kind == "brief",
        )
    ).all():
        if sid:
            researched.add(sid)
    return {sid: ("researched" if sid in researched else "backlog") for sid in ids}


def securities_needing_coverage(session: Session, *, limit: int = 50) -> list[CoverageItem]:
    """Open holdings + watchlist members lacking research coverage (thesis/docs/brief)."""
    open_ids, watch_ids = _book_security_id_sets(session)
    candidates = sorted(open_ids | watch_ids)
    status = research_status_by_security(session, candidates)
    out: list[CoverageItem] = []
    for security_id in candidates:
        if status.get(security_id) == "researched":
            continue
        reason = "open_holding" if security_id in open_ids else "watchlist"
        out.append(CoverageItem(security_id=security_id, reason=reason))
        if len(out) >= limit:
            break
    return out


def run_coverage_briefs(
    session: Session,
    *,
    limit: int = 10,
    dry_run: bool = True,
) -> list[dict[str, object]]:
    """Optionally generate briefs for names lacking research coverage."""
    items = securities_needing_coverage(session, limit=limit)
    results: list[dict[str, object]] = []
    for item in items:
        entry: dict[str, object] = {
            "security_id": item.security_id,
            "reason": item.reason,
            "dry_run": dry_run,
        }
        if dry_run:
            results.append(entry)
            continue
        brief = generate_research_brief(session, security_id=item.security_id)
        entry["cache_hit"] = brief.cache_hit
        entry["called_llm"] = brief.called_llm
        entry["agenda_count"] = len(brief.response.get("research_agenda") or [])
        results.append(entry)
    return results


_REVIEW_DECISIONS = frozenset({"unchanged", "investigate"})


def record_review(
    session: Session,
    security_id: str,
    *,
    decision: str,
    note: str | None = None,
    created_by: str | None = None,
) -> ResearchReview | None:
    """Store one explicit review. Returns None when the security does not exist."""
    cleaned = decision.strip().lower()
    if cleaned not in _REVIEW_DECISIONS:
        raise ValueError("decision must be unchanged or investigate")
    sid = security_id.strip()
    if session.get(Security, sid) is None:
        return None
    row = ResearchReview(
        security_id=sid,
        decision=cleaned,
        note=(note or "").strip() or None,
        created_by=created_by,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def latest_review(session: Session, security_id: str) -> ResearchReview | None:
    return session.scalar(
        select(ResearchReview)
        .where(ResearchReview.security_id == security_id)
        .order_by(ResearchReview.created_at.desc(), ResearchReview.review_id.desc())
        .limit(1)
    )


def company_overview(session: Session, security_id: str) -> dict[str, object] | None:
    """Local company snapshot. Does not call a model or invent review events."""
    sid = security_id.strip()
    facts = collect_security_facts(session, sid)
    if not facts.get("found"):
        return None

    approved = get_approved_thesis(session, sid)
    saved = get_active_thesis(session, sid)
    thesis = approved or saved
    assumptions: list[str] = []
    summary: str | None = None
    if thesis is not None:
        summary = (thesis.thesis_summary or "").strip() or None
        assumptions = [
            line.strip()
            for line in (thesis.key_monitoring_variables or "").splitlines()
            if line.strip()
        ][:3]
    if approved is not None:
        approval = "approved"
    elif thesis is not None:
        approval = "unconfirmed"
    else:
        approval = "none"
    pending_id = (
        saved.thesis_id
        if saved is not None and (approved is None or saved.thesis_id != approved.thesis_id)
        else None
    )

    questions = list_goals(session, security_id=sid, open_only=True)[:3]
    review = latest_review(session, sid)
    new_docs: list[ResearchDocument] = []
    if review is not None and review.created_at is not None:
        new_docs = list(
            session.scalars(
                select(ResearchDocument)
                .where(
                    ResearchDocument.security_id == sid,
                    ResearchDocument.parse_status == "ok",
                    ResearchDocument.indexed_at > review.created_at,
                )
                .order_by(ResearchDocument.indexed_at.desc())
                .limit(8)
            ).all()
        )
    if review is None:
        new_note = "No review date is stored yet, so older documents are not shown as new."
    elif not new_docs:
        new_note = "No new documents since the last review."
    else:
        new_note = "Documents linked to this company that were indexed after the last review."
    documents = list(
        session.scalars(
            select(ResearchDocument)
            .where(
                ResearchDocument.security_id == sid,
                ResearchDocument.parse_status == "ok",
            )
            .order_by(ResearchDocument.indexed_at.desc())
            .limit(8)
        ).all()
    )
    open_eps = facts.get("open_episodes") or []
    watchlists = facts.get("watchlists") or []
    if open_eps and watchlists:
        relationship = "Held and watchlisted"
    elif open_eps:
        relationship = "Held"
    elif watchlists:
        relationship = "Watchlisted"
    else:
        relationship = "In the security master"

    return {
        "found": True,
        "security_id": sid,
        "name": facts.get("portfolio_name") or facts.get("canonical_name") or sid,
        "nse_symbol": facts.get("nse_symbol"),
        "bse_code": facts.get("bse_code"),
        "relationship": relationship,
        "thesis": {
            "approval": approval,
            "thesis_id": thesis.thesis_id if thesis is not None else None,
            "pending_thesis_id": pending_id if approved is not None else None,
            "version": thesis.version if thesis is not None else None,
            "saved_at": thesis.created_at.isoformat() if thesis is not None else None,
            "approved_at": approved.approved_at.isoformat() if approved and approved.approved_at else None,
            "summary": summary,
            "assumptions": assumptions,
        },
        "last_review": (
            None
            if review is None
            else {
                "review_id": review.review_id,
                "decision": review.decision,
                "note": review.note,
                "created_at": review.created_at.isoformat() if review.created_at else None,
            }
        ),
        "new_since_review": [
            {
                "document_id": doc.document_id,
                "title": doc.title or doc.relative_path,
                "relative_path": doc.relative_path,
                "indexed_at": doc.indexed_at.isoformat() if doc.indexed_at else None,
                "source_accessible": False,
                "reason": "Indexed after the last review",
            }
            for doc in new_docs
        ],
        "new_since_review_note": new_note,
        "questions": [
            {
                "goal_id": goal.goal_id,
                "title": goal.title,
                "status": goal.status,
                "rationale": goal.rationale,
            }
            for goal in questions
        ],
        "documents": [
            {
                "document_id": doc.document_id,
                "title": doc.title or doc.relative_path,
                "relative_path": doc.relative_path,
                "indexed_at": doc.indexed_at.isoformat() if doc.indexed_at else None,
                "source_accessible": False,
            }
            for doc in documents
        ],
    }


def documents_changed_for_security(session: Session, security_id: str) -> list[ResearchDocument]:
    """Docs currently linked to a security (delta briefs use indexer hash changes)."""
    return list(
        session.scalars(
            select(ResearchDocument)
            .where(ResearchDocument.security_id == security_id)
            .order_by(ResearchDocument.indexed_at.desc())
        ).all()
    )
