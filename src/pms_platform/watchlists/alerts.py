"""Watchlist SAST / insider alert polling and persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pms_platform.market_data.bse_corporate_disclosures import (
    CorporateDisclosureRow,
    enrich_disclosures_with_market_caps,
    fetch_insider_rows,
    fetch_sast_rows,
    normalize_insider_row,
    normalize_sast_row,
)
from pms_platform.models.watchlist import WatchlistAlert, WatchlistMember
from pms_platform.watchlists import service as wl

AlertKind = Literal["sast", "insider"]
DEFAULT_LOOKBACK_DAYS = 30


@dataclass(frozen=True)
class AlertPollResult:
    inserted: int
    skipped: int
    matched: int


def disclosure_dedupe_key(row: CorporateDisclosureRow) -> str:
    """Stable key to prevent duplicate alerts for the same disclosure."""
    disclosure = row.disclosure_date.isoformat() if row.disclosure_date else ""
    return "|".join(
        [
            row.kind,
            row.bse_code.strip(),
            disclosure,
            row.person_name.strip().casefold(),
            row.transaction_type.strip().casefold(),
            str(row.quantity or ""),
            row.regulation.strip(),
        ]
    )


def _watchlist_bse_codes(members: list[WatchlistMember]) -> dict[str, int]:
    """Map normalized BSE code → member_id."""
    mapping: dict[str, int] = {}
    for member in members:
        if member.bse_code:
            mapping[member.bse_code.strip()] = member.member_id
    return mapping


def _normalize_rows(
    kind: AlertKind,
    raw_rows: list[dict],
    *,
    start: date,
    end: date,
    bse_codes: set[str],
) -> list[CorporateDisclosureRow]:
    normalizer = normalize_sast_row if kind == "sast" else normalize_insider_row
    rows: list[CorporateDisclosureRow] = []
    for raw in raw_rows:
        row = normalizer(raw)
        if row is None or not row.bse_code:
            continue
        if row.bse_code.strip() not in bse_codes:
            continue
        if row.disclosure_date is None:
            continue
        if not (start <= row.disclosure_date <= end):
            continue
        rows.append(row)
    return rows


def fetch_disclosures_for_codes(
    *,
    kind: AlertKind,
    start: date,
    end: date,
    bse_codes: set[str],
    session: Session | None = None,
) -> list[CorporateDisclosureRow]:
    """Fetch disclosures in a date range filtered to watchlist BSE codes."""
    if not bse_codes:
        return []
    if kind == "sast":
        raw_rows = fetch_sast_rows(start, end)
    elif session is not None:
        from pms_platform.market_data.insider_store import (
            load_insider_raw_rows,
            sync_insider_days,
        )

        sync_insider_days(session, start, end)
        raw_rows = load_insider_raw_rows(session, start, end)
    else:
        raw_rows = fetch_insider_rows(start, end)
    rows = _normalize_rows(kind, raw_rows, start=start, end=end, bse_codes=bse_codes)
    return enrich_disclosures_with_market_caps(rows)


def poll_watchlist_alerts(
    session: Session,
    watchlist_id: int,
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    kinds: tuple[AlertKind, ...] = ("sast", "insider"),
) -> AlertPollResult:
    """Fetch recent SAST/insider rows and upsert alerts for watchlist members."""
    wl.get_watchlist(session, watchlist_id)
    members = wl.list_members(session, watchlist_id)
    code_to_member = _watchlist_bse_codes(members)
    if not code_to_member:
        return AlertPollResult(inserted=0, skipped=0, matched=0)

    end = date.today()
    start = end - timedelta(days=lookback_days)
    fetched_at = datetime.now(timezone.utc)
    inserted = 0
    skipped = 0
    matched = 0

    for kind in kinds:
        rows = fetch_disclosures_for_codes(
            kind=kind,
            start=start,
            end=end,
            bse_codes=set(code_to_member),
            session=session,
        )
        matched += len(rows)
        for row in rows:
            if row.bse_code.strip() not in code_to_member:
                continue
            dedupe_key = disclosure_dedupe_key(row)
            existing = session.scalar(
                select(WatchlistAlert).where(
                    WatchlistAlert.watchlist_id == watchlist_id,
                    WatchlistAlert.dedupe_key == dedupe_key,
                )
            )
            if existing is not None:
                skipped += 1
                continue
            if row.disclosure_date is None:
                continue
            session.add(
                WatchlistAlert(
                    watchlist_id=watchlist_id,
                    member_id=code_to_member.get(row.bse_code.strip()),
                    dedupe_key=dedupe_key,
                    kind=row.kind,
                    disclosure_date=row.disclosure_date,
                    bse_code=row.bse_code,
                    company_name=row.company_name,
                    person_name=row.person_name,
                    category=row.category,
                    transaction_type=row.transaction_type,
                    quantity=row.quantity,
                    value=row.value,
                    pct_pre=row.pct_pre,
                    pct_post=row.pct_post,
                    mode=row.mode,
                    regulation=row.regulation,
                    market_cap_cr=row.market_cap_cr,
                    fetched_at=fetched_at,
                )
            )
            inserted += 1

    session.flush()
    return AlertPollResult(inserted=inserted, skipped=skipped, matched=matched)


def list_alerts(
    session: Session,
    watchlist_id: int,
    *,
    unacknowledged_only: bool = False,
) -> list[WatchlistAlert]:
    wl.get_watchlist(session, watchlist_id)
    query = select(WatchlistAlert).where(WatchlistAlert.watchlist_id == watchlist_id)
    if unacknowledged_only:
        query = query.where(WatchlistAlert.acknowledged.is_(False))
    return list(
        session.scalars(
            query.order_by(
                WatchlistAlert.disclosure_date.desc(),
                WatchlistAlert.created_at.desc(),
            )
        ).all()
    )


def acknowledge_alert(
    session: Session,
    watchlist_id: int,
    alert_id: int,
) -> WatchlistAlert:
    row = session.scalar(
        select(WatchlistAlert).where(
            WatchlistAlert.watchlist_id == watchlist_id,
            WatchlistAlert.alert_id == alert_id,
        )
    )
    if row is None:
        raise wl.WatchlistAlertNotFoundError(
            f"Alert {alert_id} not found on watchlist {watchlist_id}"
        )
    row.acknowledged = True
    row.acknowledged_at = datetime.now(timezone.utc)
    session.flush()
    return row


def unacknowledged_count(session: Session, watchlist_id: int | None = None) -> int:
    query = select(func.count()).select_from(WatchlistAlert).where(
        WatchlistAlert.acknowledged.is_(False)
    )
    if watchlist_id is not None:
        query = query.where(WatchlistAlert.watchlist_id == watchlist_id)
    return session.scalar(query) or 0
