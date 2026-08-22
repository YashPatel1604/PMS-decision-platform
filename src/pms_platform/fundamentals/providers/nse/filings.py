"""NSE financial filing discovery — integrated + legacy feeds."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from pms_platform.fundamentals.providers.nse.session import NSESession

_FINANCIALS_TYPE = "Integrated Filing- Financials"


@dataclass(frozen=True)
class NseFinancialFiling:
    """Normalized filing metadata from NSE integrated or legacy API."""

    symbol: str
    period_end: date
    period_type: str  # Quarterly | Annual
    consolidated: bool
    audited: bool | None
    filing_date: datetime | None
    revision_date: datetime | None
    xbrl_url: str
    source: str  # nse_integrated | nse_legacy
    source_id: str
    cumulative: bool | None = None


def _parse_nse_date(raw: object) -> date | None:
    text = str(raw or "").strip()
    if not text:
        return None
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            try:
                return datetime.strptime(text.title(), fmt).date()
            except ValueError:
                continue
    return None


def _parse_nse_datetime(raw: object) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _consolidated_flag(raw: object) -> bool:
    text = str(raw or "").strip().casefold()
    return text in {"consolidated", "c", "yes", "y"}


def _list_integrated(
    session: NSESession,
    symbol: str,
    *,
    period: str,
    from_date: date,
    to_date: date,
) -> list[NseFinancialFiling]:
    payload = session.get_json(
        "/api/integrated-filing-results",
        params={
            "index": "equities",
            "symbol": symbol,
            "period": period,
            "from_date": from_date.strftime("%d-%m-%Y"),
            "to_date": to_date.strftime("%d-%m-%Y"),
        },
    )
    rows = payload.get("data", []) if isinstance(payload, dict) else []
    out: list[NseFinancialFiling] = []
    for row in rows:
        if row.get("type") != _FINANCIALS_TYPE:
            continue
        period_end = _parse_nse_date(row.get("qe_Date"))
        xbrl = str(row.get("xbrl") or row.get("ixbrl") or "").strip()
        if period_end is None or not xbrl:
            continue
        out.append(
            NseFinancialFiling(
                symbol=symbol,
                period_end=period_end,
                period_type=period,
                consolidated=_consolidated_flag(row.get("consolidated")),
                audited=str(row.get("audited") or "").casefold().startswith("audit"),
                filing_date=_parse_nse_datetime(row.get("broadcast_Date") or row.get("creation_Date")),
                revision_date=_parse_nse_datetime(row.get("revised_Date")),
                xbrl_url=xbrl,
                source="nse_integrated",
                source_id=str(row.get("seq_Id") or xbrl),
            )
        )
    return out


def _list_legacy(
    session: NSESession,
    symbol: str,
    *,
    period: str,
    from_date: date,
    to_date: date,
) -> list[NseFinancialFiling]:
    rows = session.get_json(
        "/api/corporates-financial-results",
        params={
            "index": "equities",
            "symbol": symbol,
            "period": period,
            "from_date": from_date.strftime("%d-%m-%Y"),
            "to_date": to_date.strftime("%d-%m-%Y"),
        },
    )
    if not isinstance(rows, list):
        return []
    out: list[NseFinancialFiling] = []
    for row in rows:
        period_end = _parse_nse_date(row.get("toDate"))
        xbrl = str(row.get("xbrl") or "").strip()
        if period_end is None or not xbrl:
            continue
        cumulative = str(row.get("cumulative") or "").casefold().startswith("c")
        out.append(
            NseFinancialFiling(
                symbol=symbol,
                period_end=period_end,
                period_type=period,
                consolidated=_consolidated_flag(row.get("consolidated")),
                audited=str(row.get("audited") or "").casefold().startswith("audit"),
                filing_date=_parse_nse_datetime(row.get("filingDate") or row.get("broadCastDate")),
                revision_date=None,
                xbrl_url=xbrl,
                source="nse_legacy",
                source_id=str(row.get("seqNumber") or xbrl),
                cumulative=cumulative,
            )
        )
    return out


def _filing_rank(f: NseFinancialFiling) -> tuple[int, int, int, date]:
    """Prefer consolidated, latest revision, latest filing."""
    rev = 1 if f.revision_date else 0
    cons = 1 if f.consolidated else 0
    filed = f.filing_date or datetime.min
    return (cons, rev, int(filed.timestamp()), f.period_end)


def merge_filings(*groups: list[NseFinancialFiling]) -> list[NseFinancialFiling]:
    """Dedupe by period end + period type; pick best revision/consolidated filing."""
    best: dict[tuple[str, date, str], NseFinancialFiling] = {}
    for group in groups:
        for filing in group:
            key = (filing.symbol, filing.period_end, filing.period_type)
            existing = best.get(key)
            if existing is None or _filing_rank(filing) > _filing_rank(existing):
                best[key] = filing
    return sorted(best.values(), key=lambda f: f.period_end)


def list_nse_financial_filings(
    session: NSESession,
    symbol: str,
    *,
    years_back: int = 6,
    today: date | None = None,
) -> list[NseFinancialFiling]:
    """Merged quarterly + annual filing history for one NSE symbol."""
    clock = today or date.today()
    from_date = date(clock.year - years_back, clock.month, clock.day)
    quarterly = merge_filings(
        _list_integrated(session, symbol, period="Quarterly", from_date=from_date, to_date=clock),
        _list_legacy(session, symbol, period="Quarterly", from_date=from_date, to_date=clock),
    )
    annual = merge_filings(
        _list_integrated(session, symbol, period="Annual", from_date=from_date, to_date=clock),
        _list_legacy(session, symbol, period="Annual", from_date=from_date, to_date=clock),
    )
    return quarterly + annual
