"""Persist BSE insider filings day-by-day.

BSE ``getCorp_Regulation_ng`` market-wide search (empty scripCode) returns at
most 25 rows. A month-range call therefore only keeps the newest day. Querying
one calendar day at a time is the website's own search path; we store each day
so history survives after it falls off that 25-row window.

When a day hits the 25-row cap, we also fetch watchlist BSE codes one scrip at
a time and merge, so PMS names are not dropped even if the rest of the market
is incomplete.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.market_data.bse_corporate_disclosures import fetch_insider_rows
from pms_platform.models.insider_disclosure_day import InsiderDisclosureDay
from pms_platform.models.watchlist import WatchlistMember

# ponytail: BSE search page size. Upgrade if they ever expose pagination.
_BSE_SEARCH_CAP = 25
_FETCH_WORKERS = 4


def _date_range(start: date, end: date) -> list[date]:
    if end < start:
        return []
    days: list[date] = []
    cursor = start
    while cursor <= end:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


def _watchlist_bse_codes(session: Session) -> list[str]:
    codes: set[str] = set()
    for raw in session.scalars(
        select(WatchlistMember.bse_code).where(WatchlistMember.bse_code.is_not(None))
    ):
        code = str(raw).strip()
        if code:
            codes.add(code)
    return sorted(codes)


def _scrip_code(row: dict[str, Any]) -> str:
    return str(row.get("Fld_ScripCode") or "").strip()


def _merge_insider_rows(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[object] = set()
    for group in groups:
        for row in group:
            key = row.get("Fld_ID")
            if key is None:
                merged.append(dict(row))
                continue
            if key in seen:
                continue
            seen.add(key)
            merged.append(dict(row))
    return merged


def _needs_fetch(
    row: InsiderDisclosureDay | None,
    day: date,
    today: date,
    coverage: list[str],
) -> bool:
    if row is None or day == today:
        return True
    # Historical truncated days: one backfill pass after watchlist codes exist.
    return bool(row.truncated) and bool(coverage)


def _store_day(
    session: Session,
    day: date,
    raw_rows: list[dict[str, Any]],
    *,
    now: datetime,
    truncated: bool,
) -> InsiderDisclosureDay:
    payload = [dict(row) for row in raw_rows]
    existing = session.get(InsiderDisclosureDay, day)
    if existing is None:
        existing = InsiderDisclosureDay(disclosure_date=day)
        session.add(existing)
    existing.rows = payload
    existing.row_count = len(payload)
    existing.truncated = truncated
    existing.fetched_at = now
    return existing


def sync_insider_days(
    session: Session,
    start: date,
    end: date,
    *,
    today: date | None = None,
) -> int:
    """Fetch missing/today insider days from BSE and upsert. Returns days fetched."""
    today = today or date.today()
    days = _date_range(start, end)
    if not days:
        return 0

    coverage = _watchlist_bse_codes(session)
    existing = {
        row.disclosure_date: row
        for row in session.scalars(
            select(InsiderDisclosureDay).where(
                InsiderDisclosureDay.disclosure_date >= start,
                InsiderDisclosureDay.disclosure_date <= end,
            )
        )
    }
    pending = [
        day for day in days if _needs_fetch(existing.get(day), day, today, coverage)
    ]
    if not pending:
        return 0

    fetched: dict[date, list[dict[str, Any]]] = {}
    workers = min(_FETCH_WORKERS, len(pending))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_insider_rows, day, day): day for day in pending}
        for future in as_completed(futures):
            day = futures[future]
            fetched[day] = future.result()

    extras: dict[date, list[dict[str, Any]]] = {day: [] for day in pending}
    scrip_jobs: list[tuple[date, str]] = []
    for day in pending:
        rows = fetched.get(day, [])
        if len(rows) < _BSE_SEARCH_CAP or not coverage:
            continue
        present = {_scrip_code(row) for row in rows}
        for code in coverage:
            if code not in present:
                scrip_jobs.append((day, code))
    if scrip_jobs:
        workers = min(_FETCH_WORKERS, len(scrip_jobs))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(fetch_insider_rows, day, day, code): (day, code)
                for day, code in scrip_jobs
            }
            for future in as_completed(futures):
                day, _code = futures[future]
                extras[day].extend(future.result())

    now = datetime.now(timezone.utc)
    for day in pending:
        market = fetched.get(day, [])
        extra = extras.get(day, [])
        merged = _merge_insider_rows(market, extra) if extra else market
        # ponytail: market-wide search is still capped; truncated=False after we
        # attempted watchlist scrip backfill so historical days are not refetched.
        covered = bool(coverage) and len(market) >= _BSE_SEARCH_CAP
        truncated = len(market) >= _BSE_SEARCH_CAP and not covered
        _store_day(session, day, merged, now=now, truncated=truncated)
    session.flush()
    return len(pending)


def load_insider_raw_rows(
    session: Session,
    start: date,
    end: date,
) -> list[dict[str, Any]]:
    """Return stored raw BSE rows for dates in [start, end]."""
    rows: list[dict[str, Any]] = []
    stored = session.scalars(
        select(InsiderDisclosureDay)
        .where(
            InsiderDisclosureDay.disclosure_date >= start,
            InsiderDisclosureDay.disclosure_date <= end,
        )
        .order_by(InsiderDisclosureDay.disclosure_date)
    )
    for day_row in stored:
        rows.extend(day_row.rows or [])
    return rows
