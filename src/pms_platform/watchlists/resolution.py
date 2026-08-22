"""Watchlist symbol resolution: security master → BSE universe → Yahoo."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from pms_platform.market_data.bse_scrip_universe import resolve_bse_code
from pms_platform.market_data.yahoo_finance import YahooFinanceClient, YahooSearchHit
from pms_platform.models import Security
from pms_platform.models.watchlist import WatchlistMember, WatchlistResolutionLog

ResolutionSource = Literal["MASTER", "BSE", "YAHOO", "MANUAL"]
ResolutionStatus = Literal["RESOLVED", "EXCHANGE_RESOLVED", "PENDING", "FAILED", "AMBIGUOUS", "UNSUPPORTED"]

RESOLVE_STALE_AFTER = timedelta(days=7)


@dataclass(frozen=True)
class ResolutionResult:
    """Outcome of resolving one watchlist member's identifiers."""

    security_id: str | None
    display_name: str
    nse_symbol: str | None
    bse_code: str | None
    isin: str | None
    status: ResolutionStatus
    source: ResolutionSource | None
    note: str | None = None


def _from_security(security: Security) -> ResolutionResult:
    nse = security.current_nse_symbol or security.historical_nse_symbol
    live_bse = resolve_bse_code(
        isin=security.isin,
        company_name=security.canonical_name or security.portfolio_name,
        nse_symbol=nse,
    )
    master_bse = (security.bse_code or "").strip() or None
    bse_code = live_bse or master_bse
    note = None
    if live_bse and master_bse and live_bse != master_bse:
        note = f"BSE code refreshed via live universe ({master_bse} → {live_bse})"
    return ResolutionResult(
        security_id=security.security_id,
        display_name=security.portfolio_name,
        nse_symbol=nse,
        bse_code=bse_code,
        isin=security.isin,
        status="RESOLVED",
        source="MASTER",
        note=note,
    )


def _lookup_security(
    session: Session,
    *,
    security_id: str | None = None,
    portfolio_name: str | None = None,
    nse_symbol: str | None = None,
    bse_code: str | None = None,
) -> Security | None:
    if security_id:
        return session.get(Security, security_id.strip())
    if portfolio_name:
        return session.scalar(
            select(Security).where(Security.portfolio_name == portfolio_name.strip())
        )
    if nse_symbol:
        sym = nse_symbol.strip().upper()
        return session.scalar(
            select(Security).where(
                or_(
                    Security.current_nse_symbol == sym,
                    Security.historical_nse_symbol == sym,
                )
            )
        )
    if bse_code:
        return session.scalar(
            select(Security).where(Security.bse_code == bse_code.strip())
        )
    return None


def _apply_bse(
    *,
    display_name: str,
    nse_symbol: str | None,
    bse_code: str | None,
    isin: str | None,
) -> ResolutionResult | None:
    code = resolve_bse_code(
        bse_code=bse_code,
        isin=isin,
        company_name=display_name,
    )
    if not code:
        return None
    return ResolutionResult(
        security_id=None,
        display_name=display_name,
        nse_symbol=nse_symbol,
        bse_code=code,
        isin=isin,
        status="EXCHANGE_RESOLVED",
        source="BSE",
        note="Matched via BSE scrip universe",
    )


def _pick_yahoo_hit(hits: list[YahooSearchHit], query: str) -> YahooSearchHit | None:
    if not hits:
        return None
    q = query.strip().casefold()
    for hit in hits:
        if hit.symbol.casefold() == q or hit.name.casefold() == q:
            return hit
    for hit in hits:
        if q in hit.name.casefold() or q in hit.symbol.casefold():
            return hit
    return hits[0]


def _from_yahoo(hit: YahooSearchHit, *, prior_name: str) -> ResolutionResult:
    nse = hit.symbol if hit.exchange == "NSE" else None
    bse = resolve_bse_code(company_name=hit.name) if hit.exchange == "BSE" else None
    if hit.exchange == "NSE" and not bse:
        bse = resolve_bse_code(company_name=hit.name)
    if hit.exchange == "BSE":
        bse = hit.symbol
    return ResolutionResult(
        security_id=None,
        display_name=hit.name or prior_name,
        nse_symbol=nse or (hit.symbol if hit.exchange == "NSE" else None),
        bse_code=bse,
        isin=None,
        status="EXCHANGE_RESOLVED",
        source="YAHOO",
        note=f"Yahoo ticker {hit.yahoo_ticker}",
    )


def resolve_identifiers(
    session: Session,
    *,
    display_name: str,
    security_id: str | None = None,
    portfolio_name: str | None = None,
    nse_symbol: str | None = None,
    bse_code: str | None = None,
    isin: str | None = None,
    yahoo_client: YahooFinanceClient | None = None,
) -> ResolutionResult:
    """Resolve a watchlist row through master → BSE → Yahoo."""
    name = (display_name or portfolio_name or nse_symbol or "").strip()
    if not name and not security_id and not nse_symbol and not bse_code:
        return ResolutionResult(
            security_id=None,
            display_name="",
            nse_symbol=None,
            bse_code=None,
            isin=None,
            status="FAILED",
            source=None,
            note="No identifiers provided",
        )

    security = _lookup_security(
        session,
        security_id=security_id,
        portfolio_name=portfolio_name or display_name,
        nse_symbol=nse_symbol,
        bse_code=bse_code,
    )
    if security is not None:
        return _from_security(security)

    nse = nse_symbol.strip().upper() if nse_symbol else None
    bse = bse_code.strip() if bse_code else None
    isin_key = isin.strip().upper() if isin else None

    bse_result = _apply_bse(
        display_name=name,
        nse_symbol=nse,
        bse_code=bse,
        isin=isin_key,
    )
    if bse_result is not None:
        if nse and not bse_result.nse_symbol:
            return ResolutionResult(
                security_id=None,
                display_name=bse_result.display_name,
                nse_symbol=nse,
                bse_code=bse_result.bse_code,
                isin=bse_result.isin,
                status="EXCHANGE_RESOLVED",
                source="BSE",
                note=bse_result.note,
            )
        return bse_result

    client = yahoo_client or YahooFinanceClient()
    query = nse or name
    try:
        hits = client.search(query, limit=8)
    except Exception as exc:
        return ResolutionResult(
            security_id=None,
            display_name=name,
            nse_symbol=nse,
            bse_code=bse,
            isin=isin_key,
            status="FAILED",
            source=None,
            note=f"Yahoo search failed: {exc}",
        )

    hit = _pick_yahoo_hit(hits, query)
    if hit is None:
        return ResolutionResult(
            security_id=None,
            display_name=name,
            nse_symbol=nse,
            bse_code=bse,
            isin=isin_key,
            status="FAILED",
            source=None,
            note="No Yahoo match for Indian equity",
        )

    yahoo_result = _from_yahoo(hit, prior_name=name)
    if yahoo_result.bse_code or yahoo_result.nse_symbol:
        return yahoo_result

    return ResolutionResult(
        security_id=None,
        display_name=yahoo_result.display_name,
        nse_symbol=yahoo_result.nse_symbol,
        bse_code=yahoo_result.bse_code,
        isin=isin_key,
        status="PENDING",
        source="YAHOO",
        note="Yahoo hit without BSE/NSE code",
    )


def resolve_manual_codes(
    session: Session,
    *,
    display_name: str,
    nse_symbol: str,
    bse_code: str,
) -> ResolutionResult:
    """Accept user-supplied NSE+BSE; security master only, else MANUAL."""
    nse = nse_symbol.strip().upper()
    bse = bse_code.strip()
    security = _lookup_security(
        session,
        portfolio_name=display_name,
        nse_symbol=nse,
        bse_code=bse,
    )
    if security is not None:
        return _from_security(security)
    return ResolutionResult(
        security_id=None,
        display_name=display_name,
        nse_symbol=nse,
        bse_code=bse,
        isin=None,
        status="EXCHANGE_RESOLVED",
        source="MANUAL",
        note="User-supplied NSE/BSE codes",
    )


def apply_resolution_to_member(member: WatchlistMember, result: ResolutionResult) -> None:
    member.security_id = result.security_id
    member.display_name = result.display_name or member.display_name
    member.nse_symbol = result.nse_symbol
    member.bse_code = result.bse_code
    member.isin = result.isin
    member.resolution_status = result.status
    member.resolution_source = result.source
    member.resolution_note = result.note
    member.resolved_at = datetime.now(timezone.utc)


def is_resolution_stale(member: WatchlistMember, *, now: datetime | None = None) -> bool:
    if member.resolution_status in {"PENDING", "FAILED", "EXCHANGE_RESOLVED", "AMBIGUOUS"}:
        return True
    if member.resolved_at is None:
        return True
    clock = now or datetime.now(timezone.utc)
    resolved = member.resolved_at
    if resolved.tzinfo is None:
        resolved = resolved.replace(tzinfo=timezone.utc)
    return clock - resolved > RESOLVE_STALE_AFTER


def log_resolution_attempt(
    session: Session,
    *,
    watchlist_id: int,
    member_id: int | None,
    status: str,
    message: str,
    source_attempted: str | None = None,
) -> None:
    session.add(
        WatchlistResolutionLog(
            watchlist_id=watchlist_id,
            member_id=member_id,
            status=status,
            message=message[:2000],
            source_attempted=source_attempted,
        )
    )
