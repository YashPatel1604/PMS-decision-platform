"""Morning brief assembly — aggressive filtering, no article dump."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.documents.indexer import index_status
from pms_platform.intelligence.events import attention_materialities, list_events
from pms_platform.models.investment_thesis import ThesisConflictFlag


def build_morning_brief(session: Session, *, lookback_days: int = 7) -> dict[str, object]:
    since = date.today() - timedelta(days=max(lookback_days, 1))
    attention = attention_materialities()
    needs_all = list_events(
        session, since=since, materialities=set(attention), limit=50
    )
    book_universes = frozenset({"holding", "watchlist"})
    needs = [e for e in needs_all if e.universe in book_universes][:25]
    holdings = list_events(
        session,
        since=since,
        materialities=set(attention) | {"INFORMATIONAL"},
        universe="holding",
        limit=25,
    )
    watchlist = list_events(
        session,
        since=since,
        materialities=set(attention) | {"INFORMATIONAL"},
        universe="watchlist",
        limit=25,
    )
    # Industry bucket reserved; keep empty until we have tagged industry events.
    industry: list = []

    open_flags = list(
        session.scalars(
            select(ThesisConflictFlag)
            .where(ThesisConflictFlag.status == "open")
            .order_by(ThesisConflictFlag.created_at.desc())
            .limit(20)
        ).all()
    )

    status = index_status(session)
    data_problems: list[dict[str, str]] = []
    if int(status.get("document_count") or 0) == 0:
        data_problems.append(
            {
                "code": "research_index_empty",
                "detail": "No research notes indexed yet — upload PDF/MD/TXT on the Research page.",
            }
        )
    for flag in open_flags:
        data_problems.append(
            {
                "code": "thesis_conflict",
                "detail": (
                    f"{flag.security_id}: {flag.assumption_affected} — {flag.what_changed}"
                ),
            }
        )

    def _event_dict(row) -> dict[str, object]:
        return {
            "event_id": row.event_id,
            "security_id": row.security_id,
            "company": row.company,
            "event_type": row.event_type,
            "event_date": row.event_date.isoformat() if row.event_date else None,
            "source": row.source,
            "summary": row.summary,
            "materiality": row.materiality,
            "materiality_reason": row.materiality_reason,
            "universe": row.universe,
            "raw_document_reference": row.raw_document_reference,
        }

    return {
        "as_of": date.today().isoformat(),
        "lookback_days": lookback_days,
        "needs_attention": [_event_dict(e) for e in needs],
        "portfolio_changes": [_event_dict(e) for e in holdings],
        "watchlist_changes": [_event_dict(e) for e in watchlist],
        "industry_developments": industry,
        "data_problems": data_problems,
        "counts": {
            "needs_attention": len(needs),
            "portfolio_changes": len(holdings),
            "watchlist_changes": len(watchlist),
            "data_problems": len(data_problems),
        },
    }
