"""Persist BSE insider filings day-by-day.

BSE ``getCorp_Regulation_ng`` search (Isdefault=2) returns at most 25 rows.
A month-range call therefore only keeps the newest day. Querying one calendar
day at a time is the website's own search path; we store each day so history
survives after it falls off that 25-row window.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.market_data.bse_corporate_disclosures import fetch_insider_rows
from pms_platform.models.insider_disclosure_day import InsiderDisclosureDay

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


def _needs_fetch(row: InsiderDisclosureDay | None, day: date, today: date) -> bool:
    if row is None:
        return True
    return day == today


def _store_day(
    session: Session,
    day: date,
    raw_rows: list[dict[str, Any]],
    *,
    now: datetime,
) -> InsiderDisclosureDay:
    payload = [dict(row) for row in raw_rows]
    existing = session.get(InsiderDisclosureDay, day)
    if existing is None:
        existing = InsiderDisclosureDay(disclosure_date=day)
        session.add(existing)
    existing.rows = payload
    existing.row_count = len(payload)
    existing.truncated = len(payload) >= _BSE_SEARCH_CAP
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

    existing = {
        row.disclosure_date: row
        for row in session.scalars(
            select(InsiderDisclosureDay).where(
                InsiderDisclosureDay.disclosure_date >= start,
                InsiderDisclosureDay.disclosure_date <= end,
            )
        )
    }
    pending = [day for day in days if _needs_fetch(existing.get(day), day, today)]
    if not pending:
        return 0

    fetched: dict[date, list[dict[str, Any]]] = {}
    workers = min(_FETCH_WORKERS, len(pending))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_insider_rows, day, day): day for day in pending}
        for future in as_completed(futures):
            day = futures[future]
            fetched[day] = future.result()

    now = datetime.now(timezone.utc)
    for day in pending:
        _store_day(session, day, fetched.get(day, []), now=now)
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
