"""BSE SAST (Reg 29 system-driven) and Insider Trading 2015 company disclosures."""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.market_data.bse_disclosed_deals import fetch_bse_market_caps
from pms_platform.market_data.bse_scrip_universe import all_active_bse_codes
from pms_platform.market_data.bse_scrip_universe import resolve_bse_code
from pms_platform.models import InvestmentEpisode, Security
from pms_platform.models.enums import EpisodeStatus
from pms_platform.models.watchlist import WatchlistMember

DisclosureKind = Literal["sast", "insider"]

_IST = ZoneInfo("Asia/Kolkata")
_BSE_API = "https://api.bseindia.com/BseIndiaAPI/api"
_SAST_URL = f"{_BSE_API}/RTAREG29_ng/w"
_INSIDER_URL = f"{_BSE_API}/getCorp_Regulation_ng/w"


@dataclass(frozen=True)
class CorporateDisclosureRow:
    """One normalized BSE corporate disclosure row."""

    kind: DisclosureKind
    disclosure_date: date | None
    bse_code: str
    company_name: str
    person_name: str
    category: str
    transaction_type: str
    quantity: Decimal | None
    value: Decimal | None
    pct_pre: Decimal | None
    pct_post: Decimal | None
    mode: str
    regulation: str
    isin: str | None = None
    market_cap_cr: Decimal | None = None
    portfolio_name: str | None = None
    in_portfolio: bool = False
    is_open: bool = False
    is_arbitrage: bool = False
    raw_notes: str | None = None


@dataclass(frozen=True)
class CorporateDisclosuresResult:
    """Disclosures for one as-of date with month availability."""

    kind: DisclosureKind
    as_of_date: date
    fetched_at: datetime
    rows: list[CorporateDisclosureRow]
    available_dates: tuple[date, ...] = ()
    portfolio_dates: tuple[date, ...] = ()

    @property
    def row_count(self) -> int:
        return len(self.rows)


class CorporateDisclosuresFetchError(RuntimeError):
    """Raised when BSE corporate disclosure fetch fails."""


def _today_ist() -> date:
    return datetime.now(_IST).date()


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    last = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


def _fmt_dmy(day: date) -> str:
    return day.strftime("%d/%m/%Y")


def _fmt_iso(day: date) -> str:
    return day.strftime("%Y-%m-%d")


def _to_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    text = str(value).strip().replace(",", "")
    if not text or text.lower() in {"nan", "none", "-", "—", "null"}:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _parse_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    if "T" in text:
        text = text.split("T", 1)[0]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _clean_text(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if text.lower() in {"nan", "none", "null"}:
        return ""
    return text


def _bse_headers(referer: str) -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Referer": referer,
    }


def _fetch_table(url: str, params: dict[str, str], *, referer: str) -> list[dict[str, Any]]:
    import httpx

    with httpx.Client(
        headers=_bse_headers(referer), timeout=90.0, follow_redirects=True
    ) as client:
        try:
            client.get("https://www.bseindia.com/")
        except Exception:
            pass
        response = client.get(url, params=params)
        response.raise_for_status()
        try:
            payload = response.json()
        except Exception as exc:
            raise CorporateDisclosuresFetchError(
                f"BSE disclosure response was not JSON ({url})"
            ) from exc
    if isinstance(payload, dict):
        table = payload.get("Table")
        if isinstance(table, list):
            return [row for row in table if isinstance(row, dict)]
        if table is None and not payload:
            return []
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    raise CorporateDisclosuresFetchError(f"Unexpected BSE disclosure payload from {url}")


def fetch_sast_rows(from_date: date, to_date: date) -> list[dict[str, Any]]:
    """SAST system-driven disclosures (Regulation 29) for a date range."""
    return _fetch_table(
        _SAST_URL,
        {
            "CompanySearch": "",
            "FromDate": _fmt_dmy(from_date),
            "ToDate": _fmt_dmy(to_date),
            "ProISIN": "",
        },
        referer="https://www.bseindia.com/corporates/regulation_29",
    )


def fetch_insider_rows(
    from_date: date,
    to_date: date,
    scrip_code: str = "",
) -> list[dict[str, Any]]:
    """Insider Trading 2015 disclosures submitted by company.

    Market-wide search (empty ``scrip_code``) is capped at 25 rows. Passing a
    BSE scrip code returns that company's filings without the market-wide cap.
    """
    return _fetch_table(
        _INSIDER_URL,
        {
            "scripCode": str(scrip_code or "").strip(),
            "Regulation": "",
            "fromDT": _fmt_iso(from_date),
            "ToDate": _fmt_iso(to_date),
            "Isdefault": "2",
        },
        referer="https://www.bseindia.com/corporates/insider_trading_new",
    )


def _bse_scrip_from_field(value: object) -> str | None:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    if not text or text.lower() in {"nan", "none", "null", "0"}:
        return None
    return text


def insider_backfill_bse_codes(session: Session) -> frozenset[str]:
    """Every active BSE equity scrip, plus portfolio/watchlist codes."""
    codes = set(all_active_bse_codes())
    for raw in session.scalars(
        select(WatchlistMember.bse_code).where(WatchlistMember.bse_code.is_not(None))
    ):
        code = _bse_scrip_from_field(raw)
        if code:
            codes.add(code)
    for raw in session.scalars(select(Security.bse_code).where(Security.bse_code.is_not(None))):
        code = _bse_scrip_from_field(raw)
        if code:
            codes.add(code)
    return frozenset(codes)


def _insider_txn_side(transaction_type: str) -> str | None:
    text = transaction_type.casefold()
    if any(token in text for token in ("acq", "buy", "purchase")):
        return "buy"
    if any(token in text for token in ("disposal", "sell", "sale")):
        return "sell"
    return None


def flag_insider_arbitrage(
    rows: list[CorporateDisclosureRow],
) -> list[CorporateDisclosureRow]:
    """Same person buy+sell the same scrip on the same day → arbitrage."""
    from collections import defaultdict

    groups: dict[tuple[date | None, str, str], list[int]] = defaultdict(list)
    for idx, row in enumerate(rows):
        if row.kind != "insider":
            continue
        person = (row.person_name or "").strip().casefold()
        code = (row.bse_code or "").strip()
        if not person or not code:
            continue
        groups[(row.disclosure_date, code, person)].append(idx)

    arb_indexes: set[int] = set()
    for indexes in groups.values():
        sides = {_insider_txn_side(rows[idx].transaction_type or "") for idx in indexes}
        if "buy" in sides and "sell" in sides:
            arb_indexes.update(indexes)

    return [
        _clone_row(row, is_arbitrage=idx in arb_indexes) for idx, row in enumerate(rows)
    ]


def normalize_sast_row(raw: dict[str, Any]) -> CorporateDisclosureRow | None:
    company = _clean_text(raw.get("ComName"))
    isin = _clean_text(raw.get("ProISIN")).upper() or None
    code = resolve_bse_code(
        bse_code=raw.get("ScripCode") or raw.get("Scripcode1"),
        isin=isin,
        company_name=company,
        allow_soft_name=False,
    )
    disclosure_date = _parse_date(raw.get("DATETrans")) or _parse_date(
        raw.get("CreatedDate")
    )
    if not company and not code:
        return None
    return CorporateDisclosureRow(
        kind="sast",
        disclosure_date=disclosure_date,
        bse_code=code or "",
        company_name=company,
        person_name=_clean_text(raw.get("PromName")),
        category=_clean_text(raw.get("Promoter_NonPromoter")),
        transaction_type=_clean_text(raw.get("TransType")),
        quantity=_to_decimal(raw.get("QTYTrans")),
        value=None,
        pct_pre=_to_decimal(raw.get("PerPreHold")),
        pct_post=_to_decimal(raw.get("PerPostHold")),
        mode=_clean_text(raw.get("TransType")),
        regulation=_clean_text(raw.get("reg29_1_2")),
        isin=isin,
        raw_notes=_clean_text(raw.get("transactiondisplay")) or None,
    )


def normalize_insider_row(raw: dict[str, Any]) -> CorporateDisclosureRow | None:
    """Normalize one BSE insider row. Uses Fld_ScripCode only — no NSE/name guesswork."""
    company = _clean_text(raw.get("Companyname"))
    code = _bse_scrip_from_field(raw.get("Fld_ScripCode"))
    if not code:
        return None
    disclosure_date = (
        _parse_date(raw.get("Fld_StampDate"))
        or _parse_date(raw.get("Fld_LetterDate"))
        or _parse_date(raw.get("Fld_DateIntimation"))
    )
    if not company and not code:
        return None
    return CorporateDisclosureRow(
        kind="insider",
        disclosure_date=disclosure_date,
        bse_code=code or "",
        company_name=company,
        person_name=_clean_text(raw.get("Fld_PromoterName")),
        category=_clean_text(raw.get("Fld_PersonCatgName")),
        transaction_type=_clean_text(raw.get("Fld_TransactionType")),
        quantity=_to_decimal(raw.get("Fld_SecurityNo")),
        value=_to_decimal(raw.get("Fld_SecurityValue")),
        pct_pre=_to_decimal(raw.get("Fld_PercentofShareholdingPre")),
        pct_post=_to_decimal(raw.get("Fld_PercentofShareholdingPost")),
        mode=_clean_text(raw.get("ModeOfAquisation") or raw.get("Fld_ModeofAcquisition")),
        regulation="PIT 7(2)",
        raw_notes=_clean_text(raw.get("Fld_Notes")) or None,
    )


def _clone_row(row: CorporateDisclosureRow, **kwargs: Any) -> CorporateDisclosureRow:
    return CorporateDisclosureRow(
        kind=kwargs.get("kind", row.kind),
        disclosure_date=kwargs.get("disclosure_date", row.disclosure_date),
        bse_code=kwargs.get("bse_code", row.bse_code),
        company_name=kwargs.get("company_name", row.company_name),
        person_name=kwargs.get("person_name", row.person_name),
        category=kwargs.get("category", row.category),
        transaction_type=kwargs.get("transaction_type", row.transaction_type),
        quantity=kwargs.get("quantity", row.quantity),
        value=kwargs.get("value", row.value),
        pct_pre=kwargs.get("pct_pre", row.pct_pre),
        pct_post=kwargs.get("pct_post", row.pct_post),
        mode=kwargs.get("mode", row.mode),
        regulation=kwargs.get("regulation", row.regulation),
        isin=kwargs.get("isin", row.isin),
        market_cap_cr=kwargs.get("market_cap_cr", row.market_cap_cr),
        portfolio_name=kwargs.get("portfolio_name", row.portfolio_name),
        in_portfolio=kwargs.get("in_portfolio", row.in_portfolio),
        is_open=kwargs.get("is_open", row.is_open),
        is_arbitrage=kwargs.get("is_arbitrage", row.is_arbitrage),
        raw_notes=kwargs.get("raw_notes", row.raw_notes),
    )


def _portfolio_lookup(session: Session) -> dict[str, tuple[str, bool]]:
    open_ids = set(
        session.scalars(
            select(InvestmentEpisode.security_id).where(
                InvestmentEpisode.status == EpisodeStatus.OPEN.value
            )
        ).all()
    )
    lookup: dict[str, tuple[str, bool]] = {}

    def _put(key: str | None, name: str, is_open: bool) -> None:
        if not key:
            return
        normalized = key.strip().upper()
        if not normalized:
            return
        existing = lookup.get(normalized)
        if existing is None or (is_open and not existing[1]):
            lookup[normalized] = (name, is_open)

    for sec in session.scalars(select(Security)).all():
        is_open = sec.security_id in open_ids
        _put(sec.bse_code, sec.portfolio_name, is_open)
        _put(sec.current_nse_symbol, sec.portfolio_name, is_open)
        _put(sec.historical_nse_symbol, sec.portfolio_name, is_open)
        _put(sec.isin, sec.portfolio_name, is_open)
    return lookup


def enrich_disclosures_with_portfolio(
    rows: list[CorporateDisclosureRow], session: Session
) -> list[CorporateDisclosureRow]:
    lookup = _portfolio_lookup(session)
    out: list[CorporateDisclosureRow] = []
    for row in rows:
        match = None
        if row.bse_code:
            match = lookup.get(row.bse_code.strip().upper())
        if match is None and row.isin:
            match = lookup.get(row.isin.strip().upper())
        if match is None:
            out.append(row)
            continue
        name, is_open = match
        out.append(
            _clone_row(
                row,
                portfolio_name=name,
                in_portfolio=True,
                is_open=is_open,
            )
        )
    return out


def enrich_disclosures_with_market_caps(
    rows: list[CorporateDisclosureRow],
) -> list[CorporateDisclosureRow]:
    codes = [r.bse_code for r in rows if r.bse_code]
    if not codes:
        return rows
    caps = fetch_bse_market_caps(codes)
    return [
        _clone_row(r, market_cap_cr=caps.get(r.bse_code) if r.bse_code else None)
        for r in rows
    ]


def fetch_corporate_disclosures(
    kind: DisclosureKind,
    session: Session | None = None,
    *,
    as_of_date: date | None = None,
    calendar_month: str | None = None,
    enrich_market_cap: bool = True,
    refresh_insider: bool = False,
) -> CorporateDisclosuresResult:
    """Fetch SAST or Insider disclosures for a session date with month availability."""
    today = _today_ist()
    month_year: int | None = None
    month_num: int | None = None
    if calendar_month:
        try:
            year_s, month_s = calendar_month.split("-", 1)
            month_year, month_num = int(year_s), int(month_s)
        except ValueError as exc:
            raise CorporateDisclosuresFetchError(
                f"Invalid calendar_month {calendar_month!r}; expected YYYY-MM"
            ) from exc
    elif as_of_date is not None:
        month_year, month_num = as_of_date.year, as_of_date.month

    if month_year is not None and month_num is not None:
        start, end = _month_bounds(month_year, month_num)
        if as_of_date is not None:
            start = min(start, as_of_date)
            end = max(end, as_of_date)
        end = min(end, today)
    elif kind == "insider" and session is not None:
        start, end = _month_bounds(today.year, today.month)
        end = min(end, today)
    else:
        end = today
        start = date.fromordinal(max(end.toordinal() - 45, date(2018, 1, 1).toordinal()))

    try:
        if kind == "sast":
            raw_rows = fetch_sast_rows(start, end)
            normalized = [
                row
                for raw in raw_rows
                if (row := normalize_sast_row(raw)) is not None
            ]
        else:
            if session is not None:
                from pms_platform.market_data.insider_store import (
                    load_insider_raw_rows,
                    sync_insider_days,
                )

                if refresh_insider:
                    sync_insider_days(
                        session, start, end, today=today, scrip_backfill=False
                    )
                    session.commit()
                raw_rows = load_insider_raw_rows(session, start, end)
            else:
                raw_rows = fetch_insider_rows(start, end)
            normalized = [
                row
                for raw in raw_rows
                if (row := normalize_insider_row(raw)) is not None
            ]
    except CorporateDisclosuresFetchError:
        raise
    except Exception as exc:
        raise CorporateDisclosuresFetchError(
            f"Failed to fetch BSE {kind} disclosures: {exc}"
        ) from exc

    if session is not None:
        normalized = enrich_disclosures_with_portfolio(normalized, session)

    if kind == "insider":
        normalized = flag_insider_arbitrage(normalized)

    available = tuple(
        sorted(
            {
                r.disclosure_date
                for r in normalized
                if r.disclosure_date is not None
            },
            reverse=True,
        )
    )
    portfolio_dates = tuple(
        sorted(
            {
                r.disclosure_date
                for r in normalized
                if r.disclosure_date is not None and r.in_portfolio
            },
            reverse=True,
        )
    )
    if as_of_date is not None:
        target = as_of_date
    elif available:
        target = available[0]
    else:
        target = today

    rows = [r for r in normalized if r.disclosure_date == target]
    if enrich_market_cap:
        rows = enrich_disclosures_with_market_caps(rows)

    rows = sorted(
        rows,
        key=lambda r: (
            (r.company_name or "").casefold(),
            r.bse_code,
            (r.person_name or "").casefold(),
            r.transaction_type,
        ),
    )
    return CorporateDisclosuresResult(
        kind=kind,
        as_of_date=target,
        fetched_at=datetime.now(timezone.utc),
        rows=rows,
        available_dates=available,
        portfolio_dates=portfolio_dates,
    )
