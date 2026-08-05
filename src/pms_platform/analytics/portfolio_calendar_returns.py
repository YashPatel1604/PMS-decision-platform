"""Official PMS calendar-year returns for portfolio period comparisons.

``PORT %`` on Holdings must NOT use raw AUM start→end (that includes net
contributions). Prefer the Research ``CAGR_PMS.xlsx`` calendar-year returns
(shipped as CSV for Dad's Docker) linked across the comparison window.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from pms_platform.config import settings

_ONE = Decimal("1")
_HUNDRED = Decimal("100")
_DAYS_PER_YEAR = Decimal("365")

PORTFOLIO_CALENDAR_REL = "portfolio/pms_calendar_returns.csv"


@dataclass(frozen=True)
class CalendarYearReturn:
    """One calendar-year total return (decimal fraction, e.g. 0.25 = +25%)."""

    year: int
    portfolio_return: Decimal
    bse_smallcap_return: Decimal | None = None
    source: str = "CAGR_PMS"


def resolve_portfolio_calendar_path(external_dir: Path | None = None) -> Path | None:
    """Prefer external/OneDrive copy, then Docker seed."""
    candidates: list[Path] = []
    if external_dir is not None:
        candidates.append(Path(external_dir) / PORTFOLIO_CALENDAR_REL)
    candidates.append(Path(settings.external_data_dir) / PORTFOLIO_CALENDAR_REL)
    candidates.append(Path("/data/external") / PORTFOLIO_CALENDAR_REL)
    candidates.append(Path("/data/external_seed") / PORTFOLIO_CALENDAR_REL)
    candidates.append(Path("docker/market_data_seed") / PORTFOLIO_CALENDAR_REL)
    for path in candidates:
        if path.is_file():
            return path.resolve()
    return None


def load_portfolio_calendar_returns(
    path: Path | None = None,
) -> dict[int, CalendarYearReturn]:
    """Load calendar-year returns keyed by four-digit year."""
    resolved = path or resolve_portfolio_calendar_path()
    if resolved is None:
        return {}
    out: dict[int, CalendarYearReturn] = {}
    with resolved.open(newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            year_raw = str(raw.get("year") or "").strip()
            if not year_raw:
                continue
            year = int(year_raw)
            if year < 100:
                year += 2000
            port = Decimal(str(raw["portfolio_return"]))
            bse_raw = raw.get("bse_smallcap_return")
            bse = Decimal(str(bse_raw)) if bse_raw not in (None, "") else None
            out[year] = CalendarYearReturn(
                year=year,
                portfolio_return=port,
                bse_smallcap_return=bse,
                source=str(raw.get("source") or "CAGR_PMS"),
            )
    return out


@lru_cache(maxsize=1)
def _cached_calendar() -> tuple[tuple[int, CalendarYearReturn], ...]:
    return tuple(sorted(load_portfolio_calendar_returns().items()))


def clear_portfolio_calendar_cache() -> None:
    _cached_calendar.cache_clear()


def linked_portfolio_return_pct(
    start_date: date,
    end_date: date,
    *,
    calendar: dict[int, CalendarYearReturn] | None = None,
) -> Decimal | None:
    """Link calendar-year returns across ``[start_date, end_date]``.

    Full years use the published CY return. Partial first/last years scale with
    ``(1+r) ** (days_in_window / 365)`` so short windows stay well-defined.
    """
    if end_date < start_date:
        return None
    years = calendar if calendar is not None else dict(_cached_calendar())
    if not years:
        return None

    growth = _ONE
    year = start_date.year
    while year <= end_date.year:
        row = years.get(year)
        if row is None:
            return None
        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)
        window_start = max(start_date, year_start)
        window_end = min(end_date, year_end)
        days = (window_end - window_start).days + 1
        if days <= 0:
            year += 1
            continue
        if window_start == year_start and window_end == year_end:
            growth *= _ONE + row.portfolio_return
        else:
            fraction = Decimal(days) / _DAYS_PER_YEAR
            growth *= (_ONE + row.portfolio_return) ** fraction
        year += 1

    return (growth - _ONE) * _HUNDRED


def write_portfolio_calendar_csv(
    path: Path,
    rows: list[CalendarYearReturn],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["year", "portfolio_return", "bse_smallcap_return", "source"],
        )
        writer.writeheader()
        for row in sorted(rows, key=lambda item: item.year):
            writer.writerow(
                {
                    "year": row.year,
                    "portfolio_return": f"{row.portfolio_return:f}",
                    "bse_smallcap_return": (
                        f"{row.bse_smallcap_return:f}"
                        if row.bse_smallcap_return is not None
                        else ""
                    ),
                    "source": row.source,
                }
            )


def extract_calendar_from_cagr_workbook(path: Path) -> list[CalendarYearReturn]:
    """Parse Research/Portfolio/CAGR_PMS.xlsx ``From Start`` sheet."""
    import openpyxl

    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheet = workbook["From Start"] if "From Start" in workbook.sheetnames else workbook.active
    rows: list[CalendarYearReturn] = []
    for raw in sheet.iter_rows(values_only=True):
        if not raw or raw[0] is None or raw[1] is None:
            continue
        label = str(raw[0]).strip()
        if not label.upper().startswith("CY"):
            continue
        year = int(label[2:])
        if year < 100:
            year += 2000
        port = Decimal(str(raw[1]))
        bse = Decimal(str(raw[2])) if raw[2] is not None else None
        rows.append(
            CalendarYearReturn(
                year=year,
                portfolio_return=port,
                bse_smallcap_return=bse,
                source="CAGR_PMS",
            )
        )
    workbook.close()
    return rows
