"""Portfolio surveillance events — rule-based materiality, source retained."""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from pms_platform.models.enums import EpisodeStatus
from pms_platform.models.episode import InvestmentEpisode
from pms_platform.models.insider_disclosure_day import InsiderDisclosureDay
from pms_platform.models.investment_thesis import PortfolioEvent
from pms_platform.models.security import Security
from pms_platform.models.watchlist import WatchlistMember

_MATERIALITY = frozenset({"IGNORE", "INFORMATIONAL", "WATCH", "REVIEW", "URGENT"})
_ATTENTION = frozenset({"WATCH", "REVIEW", "URGENT"})


def _dedupe(*parts: object) -> str:
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]


def _universe_for(session: Session, security_id: str | None) -> str:
    if not security_id:
        return "other"
    open_hit = session.scalar(
        select(InvestmentEpisode.episode_id)
        .where(
            InvestmentEpisode.security_id == security_id,
            InvestmentEpisode.status == EpisodeStatus.OPEN.value,
        )
        .limit(1)
    )
    if open_hit is not None:
        return "holding"
    wl = session.scalar(
        select(WatchlistMember.member_id)
        .where(WatchlistMember.security_id == security_id)
        .limit(1)
    )
    return "watchlist" if wl is not None else "other"


def upsert_event(
    session: Session,
    *,
    dedupe_key: str,
    event_type: str,
    summary: str,
    materiality: str,
    materiality_reason: str,
    source: str,
    security_id: str | None = None,
    company: str | None = None,
    event_date: date | None = None,
    source_url: str | None = None,
    source_timestamp: datetime | None = None,
    raw_document_reference: str | None = None,
    affected_thesis: str | None = None,
    confidence: str | None = "rule",
    universe: str | None = None,
    commit: bool = True,
) -> PortfolioEvent:
    level = materiality.strip().upper()
    if level not in _MATERIALITY:
        raise ValueError(f"materiality must be one of {sorted(_MATERIALITY)}")
    existing = session.scalar(
        select(PortfolioEvent).where(PortfolioEvent.dedupe_key == dedupe_key)
    )
    uni = universe or _universe_for(session, security_id)
    if existing is not None:
        existing.summary = summary
        existing.materiality = level
        existing.materiality_reason = materiality_reason
        existing.universe = uni
        if commit:
            session.commit()
            session.refresh(existing)
        return existing

    row = PortfolioEvent(
        security_id=security_id,
        company=company,
        event_type=event_type,
        event_date=event_date,
        source=source,
        source_url=source_url,
        source_timestamp=source_timestamp,
        raw_document_reference=raw_document_reference,
        summary=summary,
        materiality=level,
        materiality_reason=materiality_reason,
        affected_thesis=affected_thesis,
        confidence=confidence,
        universe=uni,
        dedupe_key=dedupe_key,
    )
    session.add(row)
    if commit:
        session.commit()
        session.refresh(row)
    return row


def _rule_materiality(text: str) -> tuple[str, str]:
    """Deterministic keyword rules only — not an LLM judgment."""
    lowered = text.lower()
    if any(k in lowered for k in ("pledge", "pledged", "encumbr")):
        return "WATCH", "Rule: share pledge / encumbrance language in filing"
    if any(k in lowered for k in ("resign", "resignation", "suspended", "fraud", "sebi order")):
        return "REVIEW", "Rule: management/regulatory stress keywords"
    if any(k in lowered for k in ("insider", "promoter", "acquisition", "disposal")):
        return "INFORMATIONAL", "Rule: insider/promoter transaction disclosure"
    return "INFORMATIONAL", "Rule: default corporate disclosure"


def _resolve_security(session: Session, name: str | None, symbol: str | None) -> Security | None:
    if symbol:
        sym = symbol.strip().upper()
        hit = session.scalar(
            select(Security)
            .where(
                or_(
                    Security.current_nse_symbol == sym,
                    Security.historical_nse_symbol == sym,
                    Security.bse_code == sym,
                )
            )
            .limit(1)
        )
        if hit is not None:
            return hit
    if name and len(name.strip()) >= 3:
        needle = name.strip().upper()
        return session.scalar(
            select(Security)
            .where(func.upper(Security.portfolio_name).like(f"%{needle}%"))
            .limit(1)
        )
    return None


def sync_insider_events(session: Session, *, days: int = 14) -> dict[str, int]:
    """Project cached insider disclosure days into portfolio_events (idempotent)."""
    start = date.today() - timedelta(days=max(days, 1))
    days_rows = session.scalars(
        select(InsiderDisclosureDay).where(InsiderDisclosureDay.disclosure_date >= start)
    ).all()
    inserted = 0
    unchanged = 0
    for day in days_rows:
        for idx, raw in enumerate(day.rows or []):
            if not isinstance(raw, dict):
                continue
            company = str(
                raw.get("company_name")
                or raw.get("company")
                or raw.get("scrip_name")
                or ""
            ).strip()
            symbol = str(raw.get("symbol") or raw.get("scrip_code") or "").strip() or None
            detail = str(
                raw.get("particulars")
                or raw.get("category")
                or raw.get("transaction_type")
                or "Insider disclosure"
            )
            summary = f"{company or symbol or 'Unknown'}: {detail}".strip()
            materiality, reason = _rule_materiality(summary)
            sec = _resolve_security(session, company or None, symbol)
            key = _dedupe("insider", day.disclosure_date.isoformat(), idx, summary)
            before = session.scalar(
                select(PortfolioEvent.event_id).where(PortfolioEvent.dedupe_key == key)
            )
            upsert_event(
                session,
                dedupe_key=key,
                event_type="insider_transaction",
                summary=summary[:2000],
                materiality=materiality,
                materiality_reason=reason,
                source="bse_insider_disclosure_days",
                security_id=sec.security_id if sec else None,
                company=company or None,
                event_date=day.disclosure_date,
                source_timestamp=day.fetched_at,
                raw_document_reference=(
                    f"insider_disclosure_days:{day.disclosure_date.isoformat()}#{idx}"
                ),
                confidence="rule",
                commit=False,
            )
            if before is None:
                inserted += 1
            else:
                unchanged += 1
    session.commit()
    return {"days": len(days_rows), "inserted": inserted, "unchanged": unchanged}


def list_events(
    session: Session,
    *,
    since: date | None = None,
    materialities: set[str] | None = None,
    universe: str | None = None,
    limit: int = 100,
) -> list[PortfolioEvent]:
    stmt = select(PortfolioEvent).order_by(
        PortfolioEvent.event_date.desc().nullslast(),
        PortfolioEvent.event_id.desc(),
    )
    if since is not None:
        stmt = stmt.where(PortfolioEvent.event_date >= since)
    if materialities:
        stmt = stmt.where(PortfolioEvent.materiality.in_(sorted(materialities)))
    if universe:
        stmt = stmt.where(PortfolioEvent.universe == universe)
    stmt = stmt.limit(limit)
    return list(session.scalars(stmt).all())


def attention_materialities() -> frozenset[str]:
    return _ATTENTION
