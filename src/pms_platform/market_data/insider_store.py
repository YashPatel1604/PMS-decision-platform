"""Persist BSE insider filings day-by-day.

BSE market-wide search returns at most 25 rows (no pagination). When a day hits
that cap we fetch every active BSE equity scrip and merge by Fld_ID so the day
is complete. Under-cap days are already complete from the market call.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.market_data.bse_corporate_disclosures import (
    fetch_insider_rows,
    insider_backfill_bse_codes,
)
from pms_platform.models.insider_disclosure_day import InsiderDisclosureDay

# ponytail: BSE search page size; no API pagination exists.
_BSE_SEARCH_CAP = 25
_RECENT_REFRESH_DAYS = 14
# ponytail: capped days need ~5k scrip calls; raise if BSE rate-limits.
_FETCH_WORKERS = 8


def _scrip_code(row: dict[str, Any]) -> str:
    text = str(row.get("Fld_ScripCode") or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def _row_disclosure_date(raw: dict[str, Any]) -> date | None:
    from pms_platform.market_data.bse_corporate_disclosures import _parse_date

    return (
        _parse_date(raw.get("Fld_StampDate"))
        or _parse_date(raw.get("Fld_LetterDate"))
        or _parse_date(raw.get("Fld_DateIntimation"))
    )


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


def _needs_fetch(row: InsiderDisclosureDay | None, day: date, today: date) -> bool:
    if row is None:
        return True
    if (today - day).days <= _RECENT_REFRESH_DAYS:
        return True
    return bool(row.truncated)


def _store_day(
    session: Session,
    day: date,
    raw_rows: list[dict[str, Any]],
    *,
    now: datetime,
    truncated: bool,
) -> InsiderDisclosureDay:
    existing = session.get(InsiderDisclosureDay, day)
    if existing is None:
        existing = InsiderDisclosureDay(disclosure_date=day)
        session.add(existing)
    existing.rows = [dict(row) for row in raw_rows]
    existing.row_count = len(raw_rows)
    existing.truncated = truncated
    existing.fetched_at = now
    return existing


def _fetch_scrip_extras_by_day(
    pending: list[date],
    codes: list[str],
) -> dict[date, list[dict[str, Any]]]:
    extras: dict[date, list[dict[str, Any]]] = {day: [] for day in pending}
    if not pending or not codes:
        return extras
    pending_set = set(pending)
    scrip_start, scrip_end = min(pending), max(pending)
    workers = min(_FETCH_WORKERS, len(codes))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(fetch_insider_rows, scrip_start, scrip_end, code): code
            for code in codes
        }
        for future in as_completed(futures):
            for row in future.result():
                day = _row_disclosure_date(row)
                if day is not None and day in pending_set:
                    extras[day].append(dict(row))
    return extras


def sync_insider_days(
    session: Session,
    start: date,
    end: date,
    *,
    today: date | None = None,
    scrip_backfill: bool = True,
) -> int:
    """Fetch missing/recent insider days from BSE and upsert. Returns days fetched."""
    today = today or date.today()
    if end < start:
        return 0
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    coverage = sorted(insider_backfill_bse_codes(session)) if scrip_backfill else []
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

    # Only capped days need the full scrip sweep — under-cap market results are complete.
    scrip_codes: set[str] = set()
    if coverage:
        for day in pending:
            rows = fetched.get(day, [])
            if len(rows) < _BSE_SEARCH_CAP:
                continue
            present = {_scrip_code(row) for row in rows if _scrip_code(row)}
            stored = existing.get(day)
            if stored and stored.rows:
                present |= {_scrip_code(row) for row in stored.rows if _scrip_code(row)}
            scrip_codes.update(code for code in coverage if code not in present)

    extras_by_day = _fetch_scrip_extras_by_day(pending, sorted(scrip_codes))
    now = datetime.now(timezone.utc)
    for day in pending:
        market = fetched.get(day, [])
        extra = extras_by_day.get(day, [])
        prior = list((existing.get(day).rows if existing.get(day) else None) or [])
        merged = _merge_insider_rows(market, extra, prior)
        if coverage and len(market) >= _BSE_SEARCH_CAP:
            truncated = False
        else:
            truncated = len(market) >= _BSE_SEARCH_CAP
        _store_day(session, day, merged, now=now, truncated=truncated)
    session.flush()
    return len(pending)


def load_insider_raw_rows(
    session: Session,
    start: date,
    end: date,
) -> list[dict[str, Any]]:
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
