"""Watchlist CRUD and member resolution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from pms_platform.models import Security
from pms_platform.models.watchlist import Watchlist, WatchlistMember
from pms_platform.watchlists import resolution as res

MAX_MEMBERS_PER_WATCHLIST = 500


class WatchlistError(ValueError):
    """Base watchlist validation error."""


class WatchlistNotFoundError(WatchlistError):
    """Watchlist id does not exist."""


class WatchlistMemberNotFoundError(WatchlistError):
    """Member id does not exist on the watchlist."""


class WatchlistAlertNotFoundError(WatchlistError):
    """Alert id does not exist on the watchlist."""


class DuplicateMemberError(WatchlistError):
    """Stock already on this watchlist."""


class WatchlistDeleteError(WatchlistError):
    """Watchlist cannot be deleted."""


@dataclass(frozen=True)
class MemberInput:
    """Fields accepted when adding a watchlist member."""

    portfolio_name: str | None = None
    security_id: str | None = None
    nse_symbol: str | None = None
    bse_code: str | None = None
    display_name: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class ResolvedMember:
    """Normalized member fields ready for persistence."""

    security_id: str | None
    display_name: str
    nse_symbol: str | None
    bse_code: str | None
    isin: str | None
    resolution_status: str
    resolution_source: str | None = None
    resolution_note: str | None = None


@dataclass(frozen=True)
class CombinedSearchHit:
    """Unified search result from security master or Yahoo."""

    source: str
    security_id: str | None
    portfolio_name: str
    nse_symbol: str | None
    bse_code: str | None
    isin: str | None
    sector: str | None
    industry: str | None
    yahoo_ticker: str | None = None


def list_watchlists(session: Session) -> list[Watchlist]:
    """Return all watchlists with member counts loaded lazily via query."""
    return list(
        session.scalars(select(Watchlist).order_by(Watchlist.is_default.desc(), Watchlist.name))
    )


def member_count(session: Session, watchlist_id: int) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(WatchlistMember)
            .where(WatchlistMember.watchlist_id == watchlist_id)
        )
        or 0
    )


def get_watchlist(session: Session, watchlist_id: int) -> Watchlist:
    row = session.get(Watchlist, watchlist_id)
    if row is None:
        raise WatchlistNotFoundError(f"Watchlist {watchlist_id} not found")
    return row


def create_watchlist(
    session: Session,
    *,
    name: str,
    description: str | None = None,
    make_default: bool = False,
) -> Watchlist:
    clean_name = name.strip()
    if not clean_name:
        raise WatchlistError("Watchlist name is required")
    existing = session.scalar(select(Watchlist).where(Watchlist.name == clean_name))
    if existing is not None:
        raise WatchlistError(f"Watchlist '{clean_name}' already exists")

    has_any = session.scalar(select(func.count()).select_from(Watchlist)) or 0
    row = Watchlist(
        name=clean_name,
        description=(description.strip() if description else None) or None,
        is_default=make_default or has_any == 0,
    )
    session.add(row)
    session.flush()

    if make_default:
        _set_default(session, row.watchlist_id)
    return row


def update_watchlist(
    session: Session,
    watchlist_id: int,
    *,
    name: str | None = None,
    description: str | None = None,
    make_default: bool | None = None,
) -> Watchlist:
    row = get_watchlist(session, watchlist_id)
    if name is not None:
        clean_name = name.strip()
        if not clean_name:
            raise WatchlistError("Watchlist name is required")
        clash = session.scalar(
            select(Watchlist).where(
                Watchlist.name == clean_name,
                Watchlist.watchlist_id != watchlist_id,
            )
        )
        if clash is not None:
            raise WatchlistError(f"Watchlist '{clean_name}' already exists")
        row.name = clean_name
    if description is not None:
        row.description = description.strip() or None
    if make_default is True:
        _set_default(session, watchlist_id)
    session.flush()
    return row


def delete_watchlist(session: Session, watchlist_id: int, *, confirm: bool) -> None:
    if not confirm:
        raise WatchlistDeleteError("Pass confirm=true to delete a watchlist")
    row = get_watchlist(session, watchlist_id)
    if row.is_default:
        others = session.scalar(
            select(func.count())
            .select_from(Watchlist)
            .where(Watchlist.watchlist_id != watchlist_id)
        )
        if others and others > 0:
            raise WatchlistDeleteError(
                "Set another watchlist as default before deleting the default list"
            )
    session.delete(row)
    remaining = list(session.scalars(select(Watchlist)))
    if remaining and not any(w.is_default for w in remaining):
        remaining[0].is_default = True
    session.flush()


def list_members(session: Session, watchlist_id: int) -> list[WatchlistMember]:
    get_watchlist(session, watchlist_id)
    return list(
        session.scalars(
            select(WatchlistMember)
            .where(WatchlistMember.watchlist_id == watchlist_id)
            .options(joinedload(WatchlistMember.security))
            .order_by(WatchlistMember.display_name)
        )
    )


def search_securities(session: Session, query: str, *, limit: int = 20) -> list[Security]:
    q = query.strip()
    if not q:
        return []
    pattern = f"%{q.lower()}%"
    return list(
        session.scalars(
            select(Security)
            .where(
                or_(
                    func.lower(Security.portfolio_name).like(pattern),
                    func.lower(Security.canonical_name).like(pattern),
                    func.lower(Security.current_nse_symbol).like(pattern),
                    func.lower(Security.historical_nse_symbol).like(pattern),
                    func.lower(Security.bse_code).like(pattern),
                    func.lower(Security.isin).like(pattern),
                )
            )
            .order_by(Security.portfolio_name)
            .limit(limit)
        )
    )


def search_securities_combined(
    session: Session,
    query: str,
    *,
    limit: int = 20,
    include_yahoo: bool = False,
) -> list[CombinedSearchHit]:
    """Search security master first. Yahoo is opt-in so typeahead stays local."""
    q = query.strip()
    if not q:
        return []
    master = search_securities(session, q, limit=limit)
    hits: list[CombinedSearchHit] = [
        CombinedSearchHit(
            source="MASTER",
            security_id=row.security_id,
            portfolio_name=row.portfolio_name,
            nse_symbol=row.current_nse_symbol or row.historical_nse_symbol,
            bse_code=row.bse_code,
            isin=row.isin,
            sector=row.sector,
            industry=row.industry,
        )
        for row in master
    ]
    if not include_yahoo or len(hits) >= limit:
        return hits[:limit]

    seen = {h.portfolio_name.casefold() for h in hits}
    seen_symbols = {s for h in hits for s in (h.nse_symbol, h.bse_code) if s}
    from pms_platform.market_data.yahoo_finance import YahooFinanceClient

    try:
        yahoo_hits = YahooFinanceClient().search(q, limit=limit)
    except Exception:
        yahoo_hits = []

    for item in yahoo_hits:
        if item.name.casefold() in seen or item.symbol in seen_symbols:
            continue
        # ponytail: skip BSE universe download on typeahead; add/resolve fills codes.
        hits.append(
            CombinedSearchHit(
                source="YAHOO",
                security_id=None,
                portfolio_name=item.name,
                nse_symbol=item.symbol if item.exchange == "NSE" else None,
                bse_code=item.symbol if item.exchange == "BSE" else None,
                isin=None,
                sector=None,
                industry=None,
                yahoo_ticker=item.yahoo_ticker,
            )
        )
        if len(hits) >= limit:
            break
    return hits[:limit]


def resolve_member_input(session: Session, data: MemberInput) -> ResolvedMember:
    """Map add-member input through the full resolution pipeline."""
    display = (data.display_name or data.portfolio_name or data.nse_symbol or "").strip()
    if not display and not data.security_id and not data.nse_symbol and not data.bse_code:
        raise WatchlistError(
            "Provide portfolio_name, security_id, nse_symbol, or display_name"
        )
    result = res.resolve_identifiers(
        session,
        display_name=display or data.nse_symbol or "Unknown",
        security_id=data.security_id,
        portfolio_name=data.portfolio_name,
        nse_symbol=data.nse_symbol,
        bse_code=data.bse_code,
    )
    return _resolved_from_result(result)


def resolve_watchlist_member(
    session: Session, watchlist_id: int, member_id: int
) -> WatchlistMember:
    """Re-run symbol resolution for one member."""
    get_watchlist(session, watchlist_id)
    member = session.scalar(
        select(WatchlistMember)
        .where(
            WatchlistMember.watchlist_id == watchlist_id,
            WatchlistMember.member_id == member_id,
        )
        .options(joinedload(WatchlistMember.security))
    )
    if member is None:
        raise WatchlistMemberNotFoundError(
            f"Member {member_id} not found on watchlist {watchlist_id}"
        )
    result = res.resolve_identifiers(
        session,
        display_name=member.display_name,
        security_id=member.security_id,
        nse_symbol=member.nse_symbol,
        bse_code=member.bse_code,
        isin=member.isin,
    )
    _apply_resolved_to_member(member, _resolved_from_result(result))
    if result.status == "FAILED":
        res.log_resolution_attempt(
            session,
            watchlist_id=watchlist_id,
            member_id=member.member_id,
            status=result.status,
            message=result.note or "Resolution failed",
            source_attempted=result.source,
        )
    session.flush()
    return member


def resolve_stale_members(session: Session, watchlist_id: int) -> dict[str, int]:
    """Re-resolve pending/failed/stale members on a watchlist."""
    get_watchlist(session, watchlist_id)
    members = list(
        session.scalars(
            select(WatchlistMember).where(WatchlistMember.watchlist_id == watchlist_id)
        )
    )
    ok = failed = skipped = 0
    for member in members:
        if not res.is_resolution_stale(member):
            skipped += 1
            continue
        result = res.resolve_identifiers(
            session,
            display_name=member.display_name,
            security_id=member.security_id,
            nse_symbol=member.nse_symbol,
            bse_code=member.bse_code,
            isin=member.isin,
        )
        _apply_resolved_to_member(member, _resolved_from_result(result))
        if result.status == "RESOLVED":
            ok += 1
        else:
            failed += 1
            res.log_resolution_attempt(
                session,
                watchlist_id=watchlist_id,
                member_id=member.member_id,
                status=result.status,
                message=result.note or "Resolution failed",
                source_attempted=result.source,
            )
    session.flush()
    return {"resolved": ok, "failed": failed, "skipped": skipped}


def update_member_symbols(
    session: Session,
    watchlist_id: int,
    member_id: int,
    *,
    display_name: str | None = None,
    nse_symbol: str | None = None,
    bse_code: str | None = None,
    notes: str | None = None,
) -> WatchlistMember:
    """Manually fix symbols, then re-resolve (source MANUAL if codes provided)."""
    get_watchlist(session, watchlist_id)
    member = session.scalar(
        select(WatchlistMember)
        .where(
            WatchlistMember.watchlist_id == watchlist_id,
            WatchlistMember.member_id == member_id,
        )
        .options(joinedload(WatchlistMember.security))
    )
    if member is None:
        raise WatchlistMemberNotFoundError(
            f"Member {member_id} not found on watchlist {watchlist_id}"
        )
    if display_name is not None:
        member.display_name = display_name.strip() or member.display_name
    if nse_symbol is not None:
        member.nse_symbol = nse_symbol.strip().upper() or None
    if bse_code is not None:
        member.bse_code = bse_code.strip() or None
    if notes is not None:
        member.notes = notes.strip() or None

    user_fixed_both = (
        nse_symbol is not None
        and bse_code is not None
        and member.nse_symbol
        and member.bse_code
    )

    if user_fixed_both:
        result = res.resolve_manual_codes(
            session,
            display_name=member.display_name,
            nse_symbol=member.nse_symbol,
            bse_code=member.bse_code,
        )
        _apply_resolved_to_member(member, _resolved_from_result(result))
    elif member.nse_symbol or member.bse_code:
        result = res.resolve_identifiers(
            session,
            display_name=member.display_name,
            nse_symbol=member.nse_symbol,
            bse_code=member.bse_code,
        )
        _apply_resolved_to_member(member, _resolved_from_result(result))
    else:
        return resolve_watchlist_member(session, watchlist_id, member_id)

    member.resolved_at = datetime.now(timezone.utc)
    session.flush()
    return member


def _resolved_from_result(result: res.ResolutionResult) -> ResolvedMember:
    return ResolvedMember(
        security_id=result.security_id,
        display_name=result.display_name,
        nse_symbol=result.nse_symbol,
        bse_code=result.bse_code,
        isin=result.isin,
        resolution_status=result.status,
        resolution_source=result.source,
        resolution_note=result.note,
    )


def _apply_resolved_to_member(member: WatchlistMember, resolved: ResolvedMember) -> None:
    member.security_id = resolved.security_id
    member.display_name = resolved.display_name
    member.nse_symbol = resolved.nse_symbol
    member.bse_code = resolved.bse_code
    member.isin = resolved.isin
    member.resolution_status = resolved.resolution_status
    member.resolution_source = resolved.resolution_source
    member.resolution_note = resolved.resolution_note
    member.resolved_at = datetime.now(timezone.utc)


def parse_pasted_names(text: str) -> list[str]:
    """Split a paste blob on newlines/commas; first-seen order, blanks dropped."""
    ordered: list[str] = []
    seen: set[str] = set()
    for chunk in text.replace(",", "\n").splitlines():
        name = chunk.strip()
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(name)
    return ordered


@dataclass(frozen=True)
class BulkAddResult:
    added: int
    skipped: int
    pending: int


def add_members_by_names(
    session: Session, watchlist_id: int, names: list[str]
) -> BulkAddResult:
    """Add pasted names. Master hits resolve now; others stay PENDING (no Yahoo)."""
    get_watchlist(session, watchlist_id)
    added = skipped = pending = 0
    for index, name in enumerate(names):
        if member_count(session, watchlist_id) >= MAX_MEMBERS_PER_WATCHLIST:
            skipped += len(names) - index
            break
        security = _lookup_master_name(session, name)
        try:
            if security is not None:
                add_member(
                    session,
                    watchlist_id,
                    MemberInput(security_id=security.security_id, display_name=name),
                )
                added += 1
                continue
            _add_pending_member(session, watchlist_id, name)
            added += 1
            pending += 1
        except DuplicateMemberError:
            skipped += 1
    session.flush()
    return BulkAddResult(added=added, skipped=skipped, pending=pending)


def _lookup_master_name(session: Session, name: str) -> Security | None:
    key = name.strip()
    if not key:
        return None
    row = session.scalar(select(Security).where(Security.portfolio_name == key))
    if row is not None:
        return row
    upper = key.upper()
    return session.scalar(
        select(Security).where(
            or_(
                Security.current_nse_symbol == upper,
                Security.historical_nse_symbol == upper,
            )
        )
    )


def _add_pending_member(session: Session, watchlist_id: int, name: str) -> WatchlistMember:
    resolved = ResolvedMember(
        security_id=None,
        display_name=name,
        nse_symbol=None,
        bse_code=None,
        isin=None,
        resolution_status="PENDING",
        resolution_source=None,
        resolution_note="Bulk paste; use Re-resolve stale for BSE/Yahoo",
    )
    _assert_not_duplicate(session, watchlist_id, resolved)
    row = WatchlistMember(
        watchlist_id=watchlist_id,
        display_name=name,
        resolution_status="PENDING",
        resolution_note=resolved.resolution_note,
        resolved_at=datetime.now(timezone.utc),
    )
    session.add(row)
    session.flush()
    return row


def add_member(session: Session, watchlist_id: int, data: MemberInput) -> WatchlistMember:
    get_watchlist(session, watchlist_id)
    count = member_count(session, watchlist_id)
    if count >= MAX_MEMBERS_PER_WATCHLIST:
        raise WatchlistError(f"Watchlist cannot exceed {MAX_MEMBERS_PER_WATCHLIST} members")

    resolved = resolve_member_input(session, data)
    _assert_not_duplicate(session, watchlist_id, resolved)

    row = WatchlistMember(
        watchlist_id=watchlist_id,
        security_id=resolved.security_id,
        display_name=resolved.display_name,
        nse_symbol=resolved.nse_symbol,
        bse_code=resolved.bse_code,
        isin=resolved.isin,
        notes=(data.notes.strip() if data.notes else None) or None,
        resolution_status=resolved.resolution_status,
        resolution_source=resolved.resolution_source,
        resolution_note=resolved.resolution_note,
        resolved_at=datetime.now(timezone.utc),
    )
    session.add(row)
    session.flush()
    return session.scalar(
        select(WatchlistMember)
        .where(WatchlistMember.member_id == row.member_id)
        .options(joinedload(WatchlistMember.security))
    ) or row


def remove_member(session: Session, watchlist_id: int, member_id: int) -> None:
    get_watchlist(session, watchlist_id)
    row = session.scalar(
        select(WatchlistMember).where(
            WatchlistMember.watchlist_id == watchlist_id,
            WatchlistMember.member_id == member_id,
        )
    )
    if row is None:
        raise WatchlistMemberNotFoundError(
            f"Member {member_id} not found on watchlist {watchlist_id}"
        )
    session.delete(row)
    session.flush()


def _set_default(session: Session, watchlist_id: int) -> None:
    for row in session.scalars(select(Watchlist)):
        row.is_default = row.watchlist_id == watchlist_id
    session.flush()


def _assert_not_duplicate(
    session: Session, watchlist_id: int, resolved: ResolvedMember
) -> None:
    if resolved.security_id:
        existing = session.scalar(
            select(WatchlistMember).where(
                WatchlistMember.watchlist_id == watchlist_id,
                WatchlistMember.security_id == resolved.security_id,
            )
        )
        if existing is not None:
            raise DuplicateMemberError(f"{resolved.display_name} is already on this watchlist")

    if resolved.nse_symbol:
        sym = resolved.nse_symbol.upper()
        existing = session.scalar(
            select(WatchlistMember).where(
                WatchlistMember.watchlist_id == watchlist_id,
                func.upper(WatchlistMember.nse_symbol) == sym,
            )
        )
        if existing is not None:
            raise DuplicateMemberError(f"{resolved.display_name} is already on this watchlist")

    if resolved.bse_code:
        existing = session.scalar(
            select(WatchlistMember).where(
                WatchlistMember.watchlist_id == watchlist_id,
                WatchlistMember.bse_code == resolved.bse_code,
            )
        )
        if existing is not None:
            raise DuplicateMemberError(f"{resolved.display_name} is already on this watchlist")

    existing_name = session.scalar(
        select(WatchlistMember).where(
            WatchlistMember.watchlist_id == watchlist_id,
            func.lower(WatchlistMember.display_name) == resolved.display_name.lower(),
            WatchlistMember.security_id.is_(None),
        )
    )
    if existing_name is not None and resolved.security_id is None:
        raise DuplicateMemberError(f"{resolved.display_name} is already on this watchlist")
