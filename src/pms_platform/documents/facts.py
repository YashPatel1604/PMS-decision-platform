"""Deterministic platform facts injected into analyst prompts (no invented numbers)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.models.enums import EpisodeStatus
from pms_platform.models.episode import InvestmentEpisode
from pms_platform.models.security import Security
from pms_platform.models.watchlist import Watchlist, WatchlistMember


def collect_security_facts(
    session: Session,
    security_id: str,
    *,
    as_of: date | None = None,
) -> dict[str, object]:
    """Gather identity + membership + episode status only.

    Never computes returns, weights, XIRR, or fair values here.
    """
    security = session.get(Security, security_id)
    if security is None:
        return {"security_id": security_id, "found": False}

    watchlists = session.execute(
        select(Watchlist.name, WatchlistMember.notes)
        .join(WatchlistMember, WatchlistMember.watchlist_id == Watchlist.watchlist_id)
        .where(WatchlistMember.security_id == security_id)
        .order_by(Watchlist.name)
    ).all()

    episodes = session.scalars(
        select(InvestmentEpisode)
        .where(InvestmentEpisode.security_id == security_id)
        .order_by(InvestmentEpisode.episode_number)
    ).all()
    open_eps = [ep for ep in episodes if ep.status == EpisodeStatus.OPEN.value]
    closed_eps = [ep for ep in episodes if ep.status != EpisodeStatus.OPEN.value]

    facts: dict[str, object] = {
        "found": True,
        "security_id": security.security_id,
        "portfolio_name": security.portfolio_name,
        "canonical_name": security.canonical_name,
        "nse_symbol": security.current_nse_symbol,
        "bse_code": security.bse_code,
        "isin": security.isin,
        "sector": security.sector,
        "industry": security.industry,
        "status": security.status,
        "watchlists": [{"name": name, "member_notes": notes} for name, notes in watchlists],
        "open_episodes": [
            {
                "episode_id": ep.episode_id,
                "episode_number": ep.episode_number,
                "entry_date": ep.entry_date.isoformat(),
                "status": ep.status,
            }
            for ep in open_eps
        ],
        "closed_episode_count": len(closed_eps),
        "as_of": as_of.isoformat() if as_of else None,
        "note": (
            "All quantitative returns/weights must come from platform analytics APIs, "
            "not from the language model."
        ),
    }
    return facts
