"""Opt-in coverage / delta helpers for research analyst loops."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.documents.analyst import generate_research_brief
from pms_platform.models.enums import EpisodeStatus
from pms_platform.models.episode import InvestmentEpisode
from pms_platform.models.research_document import ResearchDocument, ResearchGoal
from pms_platform.models.watchlist import WatchlistMember


@dataclass(frozen=True)
class CoverageItem:
    security_id: str
    reason: str


def securities_needing_coverage(session: Session, *, limit: int = 50) -> list[CoverageItem]:
    """Open holdings + watchlist members lacking open accepted goals."""
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
    candidates = sorted(open_ids | watch_ids)
    out: list[CoverageItem] = []
    for security_id in candidates:
        open_goals = session.scalar(
            select(ResearchGoal.goal_id)
            .where(
                ResearchGoal.security_id == security_id,
                ResearchGoal.status.in_(("accepted", "proposed")),
            )
            .limit(1)
        )
        if open_goals is None:
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
    """Optionally generate briefs for names lacking research goals."""
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


def documents_changed_for_security(session: Session, security_id: str) -> list[ResearchDocument]:
    """Docs currently linked to a security (delta briefs use indexer hash changes)."""
    return list(
        session.scalars(
            select(ResearchDocument)
            .where(ResearchDocument.security_id == security_id)
            .order_by(ResearchDocument.indexed_at.desc())
        ).all()
    )
