"""Canonical security identity linking for watchlist members."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Literal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from pms_platform.market_data.bse_scrip_universe import (
    all_active_bse_codes,
    lookup_bse_scrip,
    refresh_bse_scrip_universe,
    resolve_bse_code,
)
from pms_platform.market_data.identifiers import IdentifierResolver
from pms_platform.models import ImportBatch, Security, SecuritySuccessor, SecuritySymbolHistory
from pms_platform.models.daily_price import DailyPrice
from pms_platform.models.watchlist import WatchlistMember
from pms_platform.watchlists.identity_aliases import (
    POSITIVE_UNSUPPORTED,
    lookup_symbol_alias,
    lookup_watchlist_alias,
)
from pms_platform.watchlists.metric_diagnostics import bse_code

LinkageStatus = Literal[
    "CANONICALLY_LINKED",
    "EXCHANGE_RESOLVED",
    "AMBIGUOUS",
    "UNRESOLVED",
    "UNSUPPORTED",
]

# Curated overrides for abbreviated Fair Value seed names (no fuzzy guessing).
WATCHLIST_IDENTITY_OVERRIDES: dict[str, dict[str, str]] = {
    "Arrow Coated": {"bse_code": "516064", "search_name": "ARROW GREENTECH"},
    "Capital First": {"bse_code": "539437", "nse_symbol": "IDFCFIRSTB"},
    "Greenply Inds": {"bse_code": "526797"},
    "Mahindra CIE": {"bse_code": "532756", "nse_symbol": "CIEINDIA"},
    "Minda Ind": {"bse_code": "532539", "nse_symbol": "UNOMINDA"},
    "Motilal OFS": {"bse_code": "532892", "nse_symbol": "MOTILALOFS"},
    "Pennar Engg Buil": {"bse_code": "513228"},
    "Solar Inds": {"bse_code": "532725", "nse_symbol": "SOLARINDS"},
    "Tasty Bites": {"bse_code": "519091"},
    "Garware Wall": {"bse_code": "509557"},
    "Shaily Engg": {"bse_code": "501423"},
    "SterliteTech": {"bse_code": "532374", "nse_symbol": "STLTECH"},
    "Take Soln": {"bse_code": "532890", "nse_symbol": "TAKE", "search_name": "take ltd"},
}

# Minimum calendar history for watchlist price metrics (ponytail: 3y window + 52w buffer).
MIN_PRICE_HISTORY_DAYS = 365 * 3 + 30


@dataclass(frozen=True)
class CanonicalLinkResult:
    member_id: int
    display_name: str
    security_id: str | None
    linkage_status: LinkageStatus
    match_method: str | None
    confidence: str | None
    nse_symbol: str | None
    bse_code: str | None
    isin: str | None
    candidates: tuple[str, ...] = ()
    note: str | None = None


@dataclass
class IdentityLinkStats:
    linked: int = 0
    exchange_only: int = 0
    ambiguous: int = 0
    unsupported: int = 0
    already_linked: int = 0
    securities_created: int = 0
    securities_updated: int = 0
    results: list[CanonicalLinkResult] = field(default_factory=list)


def linkage_status(member: WatchlistMember) -> LinkageStatus:
    if member.security_id:
        return "CANONICALLY_LINKED"
    if member.resolution_status == "AMBIGUOUS":
        return "AMBIGUOUS"
    if member.resolution_status == "UNSUPPORTED":
        return "UNSUPPORTED"
    if member.resolution_status in {"FAILED", "PENDING"}:
        return "UNRESOLVED"
    if member.nse_symbol or bse_code(member):
        return "EXCHANGE_RESOLVED"
    return "UNRESOLVED"


def is_canonically_linked(member: WatchlistMember) -> bool:
    return member.security_id is not None


def _norm_portfolio_key(name: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]", "", name).upper()
    return text[:128] if text else "WLUNKNOWN"


def _unique_portfolio_name(session: Session, base: str, *, bse: str | None) -> str:
    candidate = base[:120]
    if bse and session.scalar(select(Security.security_id).where(Security.portfolio_name == candidate)):
        candidate = f"{candidate[:110]}_{bse}"
    if session.scalar(select(Security.security_id).where(Security.portfolio_name == candidate)):
        candidate = f"WL_{bse or candidate[:8]}"
    return candidate[:128]


def _security_id_for_bse(bse: str) -> str:
    return f"WL{bse}"


def _ensure_import_batch(session: Session) -> ImportBatch:
    batch = session.scalar(
        select(ImportBatch).where(
            ImportBatch.source_type == "watchlist_identity",
            ImportBatch.status == "completed",
        ).order_by(ImportBatch.import_batch_id.desc()).limit(1)
    )
    if batch is not None:
        return batch
    batch = ImportBatch(
        source_type="watchlist_identity",
        source_file="watchlist_identity_link",
        source_checksum="watchlist_identity_link",
        status="completed",
    )
    session.add(batch)
    session.flush()
    return batch


def _find_security_candidates(
    session: Session,
    *,
    isin: str | None,
    bse: str | None,
    nse: str | None,
    portfolio_name: str | None,
) -> list[Security]:
    candidates: dict[str, Security] = {}
    if isin:
        for row in session.scalars(select(Security).where(Security.isin == isin)).all():
            candidates[row.security_id] = row
    if bse:
        for row in session.scalars(select(Security).where(Security.bse_code == bse)).all():
            candidates[row.security_id] = row
    if nse:
        sym = nse.upper()
        for row in session.scalars(
            select(Security).where(
                or_(Security.current_nse_symbol == sym, Security.historical_nse_symbol == sym)
            )
        ).all():
            candidates[row.security_id] = row
    if portfolio_name:
        key = portfolio_name.strip()
        row = session.scalar(select(Security).where(Security.portfolio_name == key))
        if row:
            candidates[row.security_id] = row
    return list(candidates.values())


def _successor_security_id(session: Session, security_id: str) -> str | None:
    row = session.scalar(
        select(SecuritySuccessor)
        .where(
            SecuritySuccessor.predecessor_security_id == security_id,
            SecuritySuccessor.confirmed.is_(True),
        )
        .order_by(SecuritySuccessor.effective_date.desc())
        .limit(1)
    )
    return row.successor_security_id if row else None


def upsert_security_from_exchange(
    session: Session,
    *,
    bse: str | None,
    nse: str | None,
    isin: str | None,
    display_name: str,
    import_batch_id: int,
) -> tuple[Security, bool]:
    """Create or update a canonical security row from exchange metadata."""
    refresh_bse_scrip_universe()
    meta = lookup_bse_scrip(bse) if bse else None
    if meta:
        isin = isin or meta.get("isin") or None
        nse = nse or meta.get("nse_symbol") or None
        canonical = meta.get("scrip_name") or display_name
    else:
        canonical = display_name

    existing = _find_security_candidates(session, isin=isin, bse=bse, nse=nse, portfolio_name=None)
    if len(existing) > 1:
        raise ValueError(f"Ambiguous security upsert for {display_name}: {[s.security_id for s in existing]}")
    if len(existing) == 1:
        sec = existing[0]
        changed = False
        if bse and not sec.bse_code:
            sec.bse_code = bse
            changed = True
        if nse and not sec.current_nse_symbol:
            sec.current_nse_symbol = nse.upper()
            changed = True
        if isin and not sec.isin:
            sec.isin = isin
            changed = True
        if canonical and not sec.canonical_name:
            sec.canonical_name = canonical
            changed = True
        active = bse in all_active_bse_codes() if bse else None
        if active is not None and sec.status != ("ACTIVE" if active else "INACTIVE"):
            sec.status = "ACTIVE" if active else "INACTIVE"
            changed = True
        return sec, changed

    if not bse and not nse and not isin:
        raise ValueError(f"No exchange identifiers to upsert security for {display_name}")

    sec_id = _security_id_for_bse(bse) if bse else f"WLN{(nse or 'UNK').upper()}"
    existing_id = session.get(Security, sec_id)
    if existing_id is not None:
        return existing_id, False

    portfolio = _unique_portfolio_name(session, _norm_portfolio_key(display_name), bse=bse)
    active = bse in all_active_bse_codes() if bse else True
    sec = Security(
        security_id=sec_id,
        portfolio_name=portfolio,
        canonical_name=canonical,
        current_nse_symbol=nse.upper() if nse else None,
        bse_code=bse,
        isin=isin,
        status="ACTIVE" if active else "INACTIVE",
        verification_status="WATCHLIST_IDENTITY",
        import_batch_id=import_batch_id,
    )
    session.add(sec)
    session.flush()
    _bootstrap_symbol_history(session, sec, import_batch_id=import_batch_id)
    return sec, True


def _bootstrap_symbol_history(session: Session, security: Security, *, import_batch_id: int) -> None:
    from pms_platform.market_data.common import make_csv_source_key

    effective = date(2012, 1, 1)
    rows: list[tuple[str, str]] = []
    if security.current_nse_symbol:
        rows.append(("NSE", security.current_nse_symbol))
    if security.bse_code:
        rows.append(("BSE", security.bse_code))
    if security.isin:
        rows.append(("ISIN", security.isin))
    rows.append(("PORTFOLIO_NAME", security.portfolio_name))
    for idx, (symbol_type, symbol) in enumerate(rows, start=1):
        source_key = make_csv_source_key(
            f"watchlist_identity|{security.security_id}|{symbol_type}|{symbol}",
            idx,
        )
        if session.scalar(
            select(SecuritySymbolHistory).where(SecuritySymbolHistory.source_key == source_key)
        ):
            continue
        session.add(
            SecuritySymbolHistory(
                security_id=security.security_id,
                symbol_type=symbol_type,
                symbol=symbol,
                effective_from=effective,
                effective_to=None,
                source_file="watchlist_identity_link",
                source_row=idx,
                source_key=source_key,
                import_batch_id=import_batch_id,
            )
        )


def discover_exchange_ids(session: Session, member: WatchlistMember) -> tuple[str | None, str | None, str | None, str | None]:
    """Fill missing NSE/BSE/ISIN from aliases, overrides, and BSE universe."""
    name = member.display_name.strip()
    relationship: str | None = None
    alias = lookup_watchlist_alias(session, name)
    nse = (member.nse_symbol or "").strip().upper() or None
    bse = bse_code(member)
    isin = (member.isin or "").strip().upper() or None

    if alias:
        relationship = alias.relationship_type
        nse = nse or alias.nse_symbol
        bse = bse or alias.bse_code
        isin = isin or alias.isin

    override = WATCHLIST_IDENTITY_OVERRIDES.get(name)
    if override:
        bse = bse or override.get("bse_code")
        nse = nse or override.get("nse_symbol")
        search = override.get("search_name") or name
        if not bse:
            bse = resolve_bse_code(company_name=search, nse_symbol=nse, isin=isin)

    if not bse:
        bse = resolve_bse_code(
            bse_code=member.bse_code,
            isin=isin,
            company_name=name,
            nse_symbol=nse,
            allow_soft_name=False,
        )

    hist = lookup_symbol_alias(session, nse=nse, bse=bse, isin=isin)
    if hist:
        relationship = relationship or hist.relationship_type
        if hist.security_id:
            sec = session.get(Security, hist.security_id)
            if sec:
                nse = sec.current_nse_symbol or nse
                bse = sec.bse_code or bse
                isin = sec.isin or isin

    if bse and not nse:
        meta = lookup_bse_scrip(bse)
        if meta:
            nse = meta.get("nse_symbol") or nse
            isin = isin or meta.get("isin") or None

    if nse and not bse:
        bse = resolve_bse_code(nse_symbol=nse, isin=isin, allow_soft_name=False)
        if not bse and alias and alias.bse_code:
            bse = alias.bse_code

    return nse, bse, isin, relationship


def link_watchlist_member(session: Session, member: WatchlistMember) -> CanonicalLinkResult:
    """Deterministically link one member to the security master."""
    if member.security_id:
        return CanonicalLinkResult(
            member_id=member.member_id,
            display_name=member.display_name,
            security_id=member.security_id,
            linkage_status="CANONICALLY_LINKED",
            match_method="EXISTING",
            confidence="HIGH",
            nse_symbol=member.nse_symbol,
            bse_code=bse_code(member),
            isin=member.isin,
        )

    unsupported = POSITIVE_UNSUPPORTED.get(member.display_name.strip())
    if unsupported:
        member.resolution_status = "UNSUPPORTED"
        member.resolution_note = unsupported
        member.resolved_at = datetime.now(timezone.utc)
        return CanonicalLinkResult(
            member_id=member.member_id,
            display_name=member.display_name,
            security_id=None,
            linkage_status="UNSUPPORTED",
            match_method="POSITIVE_CLASSIFICATION",
            confidence="HIGH",
            nse_symbol=member.nse_symbol,
            bse_code=bse_code(member),
            isin=member.isin,
            note=unsupported,
        )

    alias = lookup_watchlist_alias(session, member.display_name.strip())
    if alias and alias.security_id:
        dup = session.scalar(
            select(WatchlistMember.member_id).where(
                WatchlistMember.watchlist_id == member.watchlist_id,
                WatchlistMember.security_id == alias.security_id,
                WatchlistMember.member_id != member.member_id,
            )
        )
        if dup is not None:
            member.resolution_status = "AMBIGUOUS"
            member.resolution_note = f"Duplicate of member {dup} for {alias.security_id}"
            return CanonicalLinkResult(
                member_id=member.member_id,
                display_name=member.display_name,
                security_id=None,
                linkage_status="AMBIGUOUS",
                match_method="DUPLICATE_WATCHLIST",
                confidence="HIGH",
                note=member.resolution_note,
            )
        member.security_id = alias.security_id
        member.nse_symbol = alias.nse_symbol or member.nse_symbol
        member.bse_code = alias.bse_code or member.bse_code
        member.isin = alias.isin or member.isin
        member.resolution_status = "RESOLVED"
        member.resolution_source = "ALIAS"
        member.resolution_note = f"{alias.relationship_type}:{alias.notes or alias.match_method}"
        member.resolved_at = datetime.now(timezone.utc)
        return CanonicalLinkResult(
            member_id=member.member_id,
            display_name=member.display_name,
            security_id=alias.security_id,
            linkage_status="CANONICALLY_LINKED",
            match_method="ALIAS",
            confidence="HIGH",
            nse_symbol=member.nse_symbol,
            bse_code=bse_code(member),
            isin=member.isin,
            note=member.resolution_note,
        )

    nse, bse, isin, relationship = discover_exchange_ids(session, member)
    member.nse_symbol = nse
    member.bse_code = bse
    member.isin = isin

    if not nse and not bse and not isin:
        member.resolution_status = "FAILED"
        member.resolution_note = "No exchange identifiers discovered"
        return CanonicalLinkResult(
            member_id=member.member_id,
            display_name=member.display_name,
            security_id=None,
            linkage_status="UNRESOLVED",
            match_method=None,
            confidence=None,
            nse_symbol=nse,
            bse_code=bse,
            isin=isin,
            note=member.resolution_note,
        )

    candidates = _find_security_candidates(
        session,
        isin=isin,
        bse=bse,
        nse=nse,
        portfolio_name=None,
    )
    if len(candidates) > 1:
        member.resolution_status = "AMBIGUOUS"
        member.resolution_note = f"Multiple master matches: {[c.security_id for c in candidates]}"
        return CanonicalLinkResult(
            member_id=member.member_id,
            display_name=member.display_name,
            security_id=None,
            linkage_status="AMBIGUOUS",
            match_method="MULTI_MATCH",
            confidence="LOW",
            nse_symbol=nse,
            bse_code=bse,
            isin=isin,
            candidates=tuple(c.security_id for c in candidates),
            note=member.resolution_note,
        )

    if len(candidates) == 1:
        sec = candidates[0]
        method = "ISIN" if isin and sec.isin == isin else "BSE" if bse and sec.bse_code == bse else "NSE"
        dup = session.scalar(
            select(WatchlistMember.member_id).where(
                WatchlistMember.watchlist_id == member.watchlist_id,
                WatchlistMember.security_id == sec.security_id,
                WatchlistMember.member_id != member.member_id,
            )
        )
        if dup is not None:
            member.resolution_status = "AMBIGUOUS"
            member.resolution_note = f"Duplicate of member {dup} for {sec.security_id}"
            return CanonicalLinkResult(
                member_id=member.member_id,
                display_name=member.display_name,
                security_id=None,
                linkage_status="AMBIGUOUS",
                match_method="DUPLICATE_WATCHLIST",
                confidence="HIGH",
                nse_symbol=nse,
                bse_code=bse,
                isin=isin,
                note=member.resolution_note,
            )
        member.security_id = sec.security_id
        member.resolution_status = "RESOLVED"
        member.resolution_source = member.resolution_source or "MASTER"
        note = f"Linked via {method}"
        if relationship:
            note = f"{relationship}:{note}"
        member.resolution_note = note
        member.resolved_at = datetime.now(timezone.utc)
        return CanonicalLinkResult(
            member_id=member.member_id,
            display_name=member.display_name,
            security_id=sec.security_id,
            linkage_status="CANONICALLY_LINKED",
            match_method=method,
            confidence="HIGH",
            nse_symbol=nse or sec.current_nse_symbol,
            bse_code=bse or sec.bse_code,
            isin=isin or sec.isin,
        )

    # Exact normalized portfolio alias — no fuzzy name match.
    norm_key = _norm_portfolio_key(member.display_name)
    alias_hits = [
        s
        for s in session.scalars(select(Security)).all()
        if _norm_portfolio_key(s.portfolio_name) == norm_key
        or (s.canonical_name and _norm_portfolio_key(s.canonical_name) == norm_key)
    ]
    if len(alias_hits) > 1:
        member.resolution_status = "AMBIGUOUS"
        member.resolution_note = f"Ambiguous alias: {[s.security_id for s in alias_hits]}"
        return CanonicalLinkResult(
            member_id=member.member_id,
            display_name=member.display_name,
            security_id=None,
            linkage_status="AMBIGUOUS",
            match_method="ALIAS",
            confidence="LOW",
            nse_symbol=nse,
            bse_code=bse,
            isin=isin,
            candidates=tuple(s.security_id for s in alias_hits),
            note=member.resolution_note,
        )
    if len(alias_hits) == 1:
        sec = alias_hits[0]
        member.security_id = sec.security_id
        member.resolution_status = "RESOLVED"
        member.resolution_source = "MASTER"
        member.resolution_note = "Linked via normalized alias"
        member.resolved_at = datetime.now(timezone.utc)
        return CanonicalLinkResult(
            member_id=member.member_id,
            display_name=member.display_name,
            security_id=sec.security_id,
            linkage_status="CANONICALLY_LINKED",
            match_method="ALIAS",
            confidence="MEDIUM",
            nse_symbol=nse or sec.current_nse_symbol,
            bse_code=bse or sec.bse_code,
            isin=isin or sec.isin,
        )

    batch = _ensure_import_batch(session)
    try:
        sec, created = upsert_security_from_exchange(
            session,
            bse=bse,
            nse=nse,
            isin=isin,
            display_name=member.display_name,
            import_batch_id=batch.import_batch_id,
        )
    except ValueError as exc:
        member.resolution_status = "EXCHANGE_RESOLVED"
        member.resolution_note = str(exc)
        return CanonicalLinkResult(
            member_id=member.member_id,
            display_name=member.display_name,
            security_id=None,
            linkage_status="EXCHANGE_RESOLVED",
            match_method="UPSERT_FAILED",
            confidence="LOW",
            nse_symbol=nse,
            bse_code=bse,
            isin=isin,
            note=str(exc),
        )

    dup = session.scalar(
        select(WatchlistMember.member_id).where(
            WatchlistMember.watchlist_id == member.watchlist_id,
            WatchlistMember.security_id == sec.security_id,
            WatchlistMember.member_id != member.member_id,
        )
    )
    if dup is not None:
        member.resolution_status = "AMBIGUOUS"
        member.resolution_note = f"Duplicate of member {dup} for {sec.security_id}"
        return CanonicalLinkResult(
            member_id=member.member_id,
            display_name=member.display_name,
            security_id=None,
            linkage_status="AMBIGUOUS",
            match_method="DUPLICATE_WATCHLIST",
            confidence="HIGH",
            nse_symbol=nse or sec.current_nse_symbol,
            bse_code=bse or sec.bse_code,
            isin=isin or sec.isin,
            note=member.resolution_note,
        )
    member.security_id = sec.security_id
    member.resolution_status = "RESOLVED"
    member.resolution_source = "EXCHANGE_UPSERT"
    note = "Created master row from exchange metadata" if created else "Updated master row"
    if relationship:
        note = f"{relationship}:{note}"
    member.resolution_note = note
    member.resolved_at = datetime.now(timezone.utc)
    return CanonicalLinkResult(
        member_id=member.member_id,
        display_name=member.display_name,
        security_id=sec.security_id,
        linkage_status="CANONICALLY_LINKED",
        match_method="EXCHANGE_UPSERT",
        confidence="HIGH" if bse and bse in all_active_bse_codes() else "MEDIUM",
        nse_symbol=nse or sec.current_nse_symbol,
        bse_code=bse or sec.bse_code,
        isin=isin or sec.isin,
        note=member.resolution_note,
    )


def normalize_exchange_only_members(session: Session, *, watchlist_id: int | None = None) -> int:
    """Downgrade RESOLVED rows that lack security_id to EXCHANGE_RESOLVED."""
    q = select(WatchlistMember).where(
        WatchlistMember.resolution_status == "RESOLVED",
        WatchlistMember.security_id.is_(None),
    )
    if watchlist_id is not None:
        q = q.where(WatchlistMember.watchlist_id == watchlist_id)
    count = 0
    for member in session.scalars(q).all():
        if member.nse_symbol or bse_code(member):
            member.resolution_status = "EXCHANGE_RESOLVED"
            count += 1
    session.flush()
    return count


def link_watchlist_members(
    session: Session,
    *,
    watchlist_id: int | None = None,
) -> IdentityLinkStats:
    """Link all watchlist members to canonical security_id where possible."""
    from pms_platform.watchlists.identity_aliases import bootstrap_identity_aliases

    bootstrap_identity_aliases(session)
    normalize_exchange_only_members(session, watchlist_id=watchlist_id)
    q = select(WatchlistMember).order_by(WatchlistMember.watchlist_id, WatchlistMember.member_id)
    if watchlist_id is not None:
        q = q.where(WatchlistMember.watchlist_id == watchlist_id)
    stats = IdentityLinkStats()
    for member in session.scalars(q).all():
        if member.security_id:
            stats.already_linked += 1
            continue
        before_created = session.scalar(select(Security.security_id).where(Security.security_id.like("WL%")))
        result = link_watchlist_member(session, member)
        stats.results.append(result)
        if result.linkage_status == "CANONICALLY_LINKED":
            stats.linked += 1
            if result.match_method == "EXCHANGE_UPSERT":
                stats.securities_created += 1
        elif result.linkage_status == "EXCHANGE_RESOLVED":
            stats.exchange_only += 1
        elif result.linkage_status == "AMBIGUOUS":
            stats.ambiguous += 1
        elif result.linkage_status == "UNSUPPORTED":
            stats.unsupported += 1
    session.flush()
    return stats


def price_history_summary(session: Session, member: WatchlistMember) -> dict[str, object]:
    """Earliest/latest price coverage for a member."""
    from pms_platform.market_data.price_returns import _load_daily_prices

    bse = bse_code(member)
    if not member.security_id and not bse:
        return {"row_count": 0, "earliest": None, "latest": None, "meets_minimum": False}
    rows = _load_daily_prices(session, "BSE_CODE", bse, as_of=date.today()) if bse else []
    if not rows and member.security_id:
        rows = list(
            session.scalars(
                select(DailyPrice)
                .where(DailyPrice.security_id == member.security_id)
                .order_by(DailyPrice.trade_date)
            ).all()
        )
    if not rows:
        return {"row_count": 0, "earliest": None, "latest": None, "meets_minimum": False}
    dates = [r.trade_date for r in rows]
    span = (max(dates) - min(dates)).days
    return {
        "row_count": len(rows),
        "earliest": min(dates).isoformat(),
        "latest": max(dates).isoformat(),
        "span_days": span,
        "meets_minimum": span >= MIN_PRICE_HISTORY_DAYS,
        "ath_is_partial": len(rows) < 500,  # ponytail: flag incomplete lifetime ATH
    }


def count_prices_without_master(session: Session) -> int:
    from sqlalchemy import func

    orphan_ids = session.scalars(
        select(DailyPrice.security_id)
        .where(DailyPrice.security_id.isnot(None))
        .distinct()
    ).all()
    if not orphan_ids:
        return 0
    master_ids = set(session.scalars(select(Security.security_id)).all())
    return sum(1 for sid in orphan_ids if sid not in master_ids)


def count_master_without_prices(session: Session) -> int:
    from sqlalchemy import func

    return session.scalar(
        select(func.count())
        .select_from(Security)
        .where(
            ~Security.security_id.in_(
                select(DailyPrice.security_id).where(DailyPrice.security_id.isnot(None)).distinct()
            )
        )
    ) or 0
