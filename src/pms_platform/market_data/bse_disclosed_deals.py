"""BSE disclosed bulk / block deals (historical form + normalize)."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Literal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.models import InvestmentEpisode, Security
from pms_platform.models.enums import EpisodeStatus

DealKind = Literal["block", "bulk"]

_IST = ZoneInfo("Asia/Kolkata")

_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "deal_date": ("deal date", "date", "dealdate", "trade date"),
    "bse_code": (
        "security code",
        "scrip code",
        "scripcode",
        "code",
        "securitycode",
        "bse code",
    ),
    "scrip_name": (
        "security name",
        "scrip name",
        "scripname",
        "company name",
        "company",
        "name",
    ),
    "client_name": ("client name", "clientname", "client", "client/firm"),
    "deal_type": ("deal type", "dealtype", "buy/sell", "type", "bs", "b/s"),
    "quantity": ("quantity", "qty", "quantity share", "traded quantity"),
    "price": (
        "price",
        "deal price",
        "trade price",
        "average price",
        "avg price",
        "weighted average price",
        "rate",
        "traded price",
    ),
}

# rblDT on bulknblockdeals.aspx: 1=Bulk, 2=Block
_RBL_DT: dict[DealKind, str] = {"bulk": "1", "block": "2"}

_BSE_HISTORY_URL = (
    "https://beta.bseindia.com/markets/equity/EQReports/bulknblockdeals.aspx?flag=1"
)
_BSE_STOCK_TRADING_URL = (
    "https://api.bseindia.com/BseIndiaAPI/api/StockTrading/w"
)
_MARKET_CAP_CACHE: dict[str, tuple[float, Decimal | None]] = {}
_MARKET_CAP_TTL_SEC = 6 * 60 * 60


def _parse_market_cap_cr(raw: object) -> Decimal | None:
    return _to_decimal(raw)


def fetch_bse_market_caps(bse_codes: list[str]) -> dict[str, Decimal | None]:
    """Fetch full market cap (₹ Cr) from BSE StockTrading for unique codes."""
    import time

    import httpx

    now = time.time()
    unique = []
    seen: set[str] = set()
    for code in bse_codes:
        normalized = str(code or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        cached = _MARKET_CAP_CACHE.get(normalized)
        if cached is not None and now - cached[0] < _MARKET_CAP_TTL_SEC:
            continue
        unique.append(normalized)

    if unique:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json,text/plain,*/*",
            "Referer": "https://www.bseindia.com/",
        }
        with httpx.Client(headers=headers, timeout=20.0, follow_redirects=True) as client:
            try:
                client.get("https://www.bseindia.com/")
            except Exception:
                pass
            for code in unique:
                try:
                    response = client.get(
                        _BSE_STOCK_TRADING_URL,
                        params={"flag": "", "quotetype": "EQ", "scripcode": code},
                    )
                    response.raise_for_status()
                    payload = response.json()
                    cap = _parse_market_cap_cr(
                        payload.get("MktCapFull") if isinstance(payload, dict) else None
                    )
                except Exception:
                    cap = None
                _MARKET_CAP_CACHE[code] = (now, cap)

    return {
        code: (
            _MARKET_CAP_CACHE[code][1]
            if code in _MARKET_CAP_CACHE
            else None
        )
        for code in seen
    }


def enrich_with_market_caps(deals: list[DisclosedDealRow]) -> list[DisclosedDealRow]:
    """Attach BSE full market cap (₹ Cr) to each deal."""
    if not deals:
        return deals
    caps = fetch_bse_market_caps([d.bse_code for d in deals])
    return [
        _clone_deal(d, market_cap_cr=caps.get(d.bse_code))
        for d in deals
    ]


def filter_deals_by_market_cap(
    deals: list[DisclosedDealRow],
    *,
    min_market_cap_cr: Decimal | None = None,
    max_market_cap_cr: Decimal | None = None,
) -> list[DisclosedDealRow]:
    """Filter deals by full market cap in ₹ Cr. Unknown caps fail a min filter."""
    if min_market_cap_cr is None and max_market_cap_cr is None:
        return deals
    out: list[DisclosedDealRow] = []
    for deal in deals:
        cap = deal.market_cap_cr
        if min_market_cap_cr is not None:
            if cap is None or cap < min_market_cap_cr:
                continue
        if max_market_cap_cr is not None:
            if cap is None or cap > max_market_cap_cr:
                continue
        out.append(deal)
    return out


_BSE_BLOCK_LATEST_URL = (
    "https://beta.bseindia.com/markets/equity/EQReports/block_deals.aspx"
)


@dataclass(frozen=True)
class DisclosedDealRow:
    """One normalized BSE bulk or block deal."""

    deal_date: date | None
    bse_code: str
    scrip_name: str
    client_name: str
    deal_type: str
    quantity: Decimal
    price: Decimal
    value: Decimal
    is_arbitrage: bool = False
    portfolio_name: str | None = None
    in_portfolio: bool = False
    is_open: bool = False
    market_cap_cr: Decimal | None = None


@dataclass(frozen=True)
class DisclosedDealsResult:
    """Disclosed deals payload for one as-of date."""

    as_of_date: date
    fetched_at: datetime
    deals: list[DisclosedDealRow]
    available_dates: tuple[date, ...] = ()
    portfolio_dates: tuple[date, ...] = ()
    kind: DealKind = "block"

    @property
    def deal_count(self) -> int:
        return len(self.deals)

    @property
    def arbitrage_deal_count(self) -> int:
        return sum(1 for d in self.deals if d.is_arbitrage)

    @property
    def non_arbitrage_deal_count(self) -> int:
        return self.deal_count - self.arbitrage_deal_count


class DisclosedDealsFetchError(RuntimeError):
    """Raised when the BSE disclosed-deals fetch fails."""


def _today_ist() -> date:
    return datetime.now(_IST).date()


def _norm_header(value: object) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[*]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _resolve_columns(columns: list[object]) -> dict[str, str]:
    by_norm = {_norm_header(c): c for c in columns}
    resolved: dict[str, str] = {}
    for field, aliases in _COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in by_norm:
                resolved[field] = str(by_norm[alias])
                break
    return resolved


def _to_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    text = str(value).strip().replace(",", "")
    if not text or text.lower() in {"nan", "none", "-", "—"}:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _parse_deal_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        return None
    for fmt in (
        "%d-%b-%Y",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y-%m-%d",
        "%d %b %Y",
        "%d/%m/%y",
        "%d-%m-%y",
    ):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _normalize_deal_type(value: object) -> str:
    text = str(value or "").strip().upper()
    if text in {"P", "PURCHASE"} or text.startswith("B"):
        return "BUY"
    if text.startswith("S"):
        return "SELL"
    return text or "UNKNOWN"


def normalize_client_name(name: str) -> str:
    """Casefold / collapse whitespace / strip trailing punctuation for firm matching."""
    text = re.sub(r"\s+", " ", (name or "").casefold()).strip()
    text = text.strip(".,;:-_|/\\")
    return text


def _clone_deal(d: DisclosedDealRow, *, is_arbitrage: bool | None = None, **kwargs: Any) -> DisclosedDealRow:
    return DisclosedDealRow(
        deal_date=kwargs.get("deal_date", d.deal_date),
        bse_code=kwargs.get("bse_code", d.bse_code),
        scrip_name=kwargs.get("scrip_name", d.scrip_name),
        client_name=kwargs.get("client_name", d.client_name),
        deal_type=kwargs.get("deal_type", d.deal_type),
        quantity=kwargs.get("quantity", d.quantity),
        price=kwargs.get("price", d.price),
        value=kwargs.get("value", d.value),
        is_arbitrage=d.is_arbitrage if is_arbitrage is None else is_arbitrage,
        portfolio_name=kwargs.get("portfolio_name", d.portfolio_name),
        in_portfolio=kwargs.get("in_portfolio", d.in_portfolio),
        is_open=kwargs.get("is_open", d.is_open),
        market_cap_cr=kwargs.get("market_cap_cr", d.market_cap_cr),
    )


def flag_arbitrage_deals(
    deals: list[DisclosedDealRow],
) -> list[DisclosedDealRow]:
    """Mark same-firm buy+sell on the same day for the same security as arbitrage.

    Quantity/value do not matter — any buy and sell pair by the same client
    in the same scrip on the same session date is treated as arb.
    """
    groups: dict[tuple[date | None, str, str], list[int]] = defaultdict(list)
    for idx, deal in enumerate(deals):
        security = (deal.bse_code or "").strip() or (deal.scrip_name or "").casefold()
        client = normalize_client_name(deal.client_name)
        if not security or not client:
            continue
        groups[(deal.deal_date, security, client)].append(idx)

    arb_indexes: set[int] = set()
    for indexes in groups.values():
        has_buy = any(deals[idx].deal_type == "BUY" for idx in indexes)
        has_sell = any(deals[idx].deal_type == "SELL" for idx in indexes)
        if has_buy and has_sell:
            arb_indexes.update(indexes)

    return [
        _clone_deal(d, is_arbitrage=idx in arb_indexes) for idx, d in enumerate(deals)
    ]


def normalize_disclosed_deals_frame(
    frame: Any, *, kind: DealKind = "block"
) -> list[DisclosedDealRow]:
    """Convert BSE deal rows (list[dict] or empty) into DisclosedDealRow list."""
    rows = _as_deal_row_dicts(frame)
    if not rows:
        return []

    columns = list(rows[0].keys())
    resolved = _resolve_columns(columns)
    required = ("bse_code", "deal_type", "quantity", "price")
    if any(field not in resolved for field in required):
        missing = [f for f in required if f not in resolved]
        raise DisclosedDealsFetchError(
            f"Unexpected BSE {kind}-deal columns (missing {missing}): {columns}"
        )

    deals: list[DisclosedDealRow] = []
    for series in rows:
        qty = _to_decimal(series.get(resolved["quantity"]))
        price = _to_decimal(series.get(resolved["price"]))
        if qty is None or price is None or qty <= 0 or price <= 0:
            continue
        code_raw = series.get(resolved["bse_code"])
        bse_code = str(code_raw).strip()
        if bse_code.endswith(".0"):
            bse_code = bse_code[:-2]
        if not bse_code or bse_code.lower() in {"nan", "none"}:
            continue
        client_col = resolved.get("client_name")
        name_col = resolved.get("scrip_name")
        date_col = resolved.get("deal_date")
        client = str(series.get(client_col) if client_col else "").strip()
        scrip = str(series.get(name_col) if name_col else "").strip()
        if client.lower() in {"nan", "none"}:
            client = ""
        if scrip.lower() in {"nan", "none"}:
            scrip = ""
        deals.append(
            DisclosedDealRow(
                deal_date=_parse_deal_date(series.get(date_col) if date_col else None),
                bse_code=bse_code,
                scrip_name=scrip,
                client_name=client,
                deal_type=_normalize_deal_type(series.get(resolved["deal_type"])),
                quantity=qty,
                price=price,
                value=qty * price,
            )
        )
    return deals


def _as_deal_row_dicts(frame: Any) -> list[dict[str, Any]]:
    if frame is None:
        return []
    if isinstance(frame, list):
        return [row for row in frame if isinstance(row, dict)]
    return []


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
    return lookup


def enrich_with_portfolio(
    deals: list[DisclosedDealRow], session: Session
) -> list[DisclosedDealRow]:
    lookup = _portfolio_lookup(session)
    out: list[DisclosedDealRow] = []
    for deal in deals:
        match = lookup.get(deal.bse_code.strip().upper())
        if match is None:
            out.append(deal)
            continue
        name, is_open = match
        out.append(
            _clone_deal(
                deal,
                portfolio_name=name,
                in_portfolio=True,
                is_open=is_open,
            )
        )
    return out


def _fmt_bse_date(day: date) -> str:
    return day.strftime("%d/%m/%Y")


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    import calendar

    last = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


def _extract_aspnet_fields(html: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for match in re.finditer(r"<input\b([^>]*)>", html, re.I):
        attrs = match.group(1)
        names = re.findall(r'\bname="([^"]*)"', attrs)
        type_match = re.search(r'\btype="([^"]*)"', attrs, re.I)
        input_type = (type_match.group(1) if type_match else "text").lower()
        if input_type in {"submit", "button", "image"} or not names:
            continue
        value_match = re.search(r'\bvalue="([^"]*)"', attrs)
        fields[names[0]] = (value_match.group(1) if value_match else "").replace(
            "&amp;", "&"
        )
    return fields


def fetch_bse_disclosed_deals_history(
    kind: DealKind, from_date: date, to_date: date
) -> list[dict[str, Any]]:
    """Historical BSE bulk/block deals via bulknblockdeals form + CSV download."""
    import csv
    from io import StringIO

    import httpx

    from pms_platform.market_data.bse_http import bse_headers

    if to_date < from_date:
        from_date, to_date = to_date, from_date

    rbl = _RBL_DT[kind]
    headers = {
        **bse_headers(referer="https://www.bseindia.com/"),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Origin": "https://beta.bseindia.com",
    }
    fro = _fmt_bse_date(from_date)
    to = _fmt_bse_date(to_date)

    with httpx.Client(headers=headers, timeout=90.0, follow_redirects=True) as client:
        get_response = client.get(_BSE_HISTORY_URL)
        get_response.raise_for_status()
        payload = _extract_aspnet_fields(get_response.text)
        payload.update(
            {
                "__EVENTTARGET": "",
                "__EVENTARGUMENT": "",
                "ctl00$ContentPlaceHolder1$rblDT": rbl,
                "ctl00$ContentPlaceHolder1$txtDate": fro,
                "ctl00$ContentPlaceHolder1$txtToDate": to,
                "ctl00$ContentPlaceHolder1$DDate": fro,
                "ctl00$ContentPlaceHolder1$chkAllMarket": "on",
                "ctl00$ContentPlaceHolder1$btnSubmit": "Submit",
            }
        )
        submit = client.post(
            _BSE_HISTORY_URL,
            data=payload,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": _BSE_HISTORY_URL,
            },
        )
        submit.raise_for_status()
        download_payload = _extract_aspnet_fields(submit.text)
        download_payload.update(
            {
                "__EVENTTARGET": "ctl00$ContentPlaceHolder1$btnDownload",
                "__EVENTARGUMENT": "",
                "ctl00$ContentPlaceHolder1$rblDT": rbl,
                "ctl00$ContentPlaceHolder1$txtDate": fro,
                "ctl00$ContentPlaceHolder1$txtToDate": to,
                "ctl00$ContentPlaceHolder1$DDate": fro,
                "ctl00$ContentPlaceHolder1$chkAllMarket": "on",
            }
        )
        csv_response = client.post(
            _BSE_HISTORY_URL,
            data=download_payload,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": _BSE_HISTORY_URL,
            },
        )
        csv_response.raise_for_status()
        submit_html = submit.text

    content_type = (csv_response.headers.get("content-type") or "").lower()
    disposition = (csv_response.headers.get("content-disposition") or "").lower()
    body = csv_response.content
    text_body = body.decode("utf-8", errors="replace")
    if "deal date" not in text_body.lower()[:500]:
        if "no record" in submit_html.lower() or len(body) < 40:
            return []
        raise DisclosedDealsFetchError(
            f"BSE {kind} history download was not CSV ({content_type=} {disposition=})"
        )
    try:
        return list(csv.DictReader(StringIO(text_body)))
    except Exception as exc:
        raise DisclosedDealsFetchError(
            f"Failed to parse BSE {kind}-deal CSV: {exc}"
        ) from exc


def _html_tables_as_dicts(html: str) -> list[list[dict[str, str]]]:
    """Parse HTML tables into list-of-row-dicts (header row → keys)."""
    from html.parser import HTMLParser

    class _Tables(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.tables: list[list[list[str]]] = []
            self._table: list[list[str]] | None = None
            self._row: list[str] | None = None
            self._cell = False
            self._parts: list[str] = []

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            del attrs
            if tag == "table":
                self._table = []
            elif tag == "tr" and self._table is not None:
                self._row = []
            elif tag in {"td", "th"} and self._row is not None:
                self._cell = True
                self._parts = []

        def handle_endtag(self, tag: str) -> None:
            if tag in {"td", "th"} and self._cell and self._row is not None:
                self._row.append(" ".join("".join(self._parts).split()))
                self._cell = False
            elif tag == "tr" and self._row is not None and self._table is not None:
                if self._row:
                    self._table.append(self._row)
                self._row = None
            elif tag == "table" and self._table is not None:
                if self._table:
                    self.tables.append(self._table)
                self._table = None

        def handle_data(self, data: str) -> None:
            if self._cell:
                self._parts.append(data)

    parser = _Tables()
    parser.feed(html)
    out: list[list[dict[str, str]]] = []
    for table in parser.tables:
        if len(table) < 2:
            continue
        headers = [h or f"col{i}" for i, h in enumerate(table[0])]
        rows: list[dict[str, str]] = []
        for raw in table[1:]:
            row = {
                headers[i]: (raw[i] if i < len(raw) else "")
                for i in range(len(headers))
            }
            rows.append(row)
        if rows:
            out.append(rows)
    return out


def _fetch_bse_beta_block_deals_frame() -> list[dict[str, Any]]:
    """Latest-session BSE block-deal HTML table (block only)."""
    import httpx

    from pms_platform.market_data.bse_http import bse_headers

    headers = {
        **bse_headers(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    with httpx.Client(headers=headers, timeout=30.0, follow_redirects=True) as client:
        response = client.get(_BSE_BLOCK_LATEST_URL)
        response.raise_for_status()
        html = response.text
    tables = _html_tables_as_dicts(html)
    for table in tables:
        cols = {_norm_header(c) for c in table[0].keys()}
        if "deal date" in cols and ("security code" in cols or "scrip code" in cols):
            return table
    if len(tables) >= 2:
        return tables[1]
    if tables:
        return tables[0]
    raise DisclosedDealsFetchError("BSE block-deals page returned no HTML tables")


def fetch_disclosed_deals(
    kind: DealKind,
    session: Session | None = None,
    *,
    fetch_frame: Callable[[], Any] | None = None,
    as_of_date: date | None = None,
    calendar_month: str | None = None,
) -> DisclosedDealsResult:
    """Fetch BSE bulk or block deals for a session date with month availability."""
    today = _today_ist()
    month_year: int | None = None
    month_num: int | None = None
    if calendar_month:
        try:
            month_year_s, month_num_s = calendar_month.split("-", 1)
            month_year, month_num = int(month_year_s), int(month_num_s)
        except ValueError as exc:
            raise DisclosedDealsFetchError(
                f"Invalid calendar_month {calendar_month!r}; expected YYYY-MM"
            ) from exc
    elif as_of_date is not None:
        month_year, month_num = as_of_date.year, as_of_date.month

    if fetch_frame is not None:
        try:
            frame = fetch_frame()
        except Exception as exc:
            raise DisclosedDealsFetchError(
                f"Failed to fetch {kind} deals: {exc}"
            ) from exc
    elif month_year is not None and month_num is not None:
        start, end = _month_bounds(month_year, month_num)
        if as_of_date is not None:
            start = min(start, as_of_date)
            end = max(end, as_of_date)
        end = min(end, today)
        try:
            frame = fetch_bse_disclosed_deals_history(kind, start, end)
        except DisclosedDealsFetchError:
            raise
        except Exception as exc:
            raise DisclosedDealsFetchError(
                f"Failed to fetch BSE historical {kind} deals: {exc}"
            ) from exc
    else:
        end = today
        start = date.fromordinal(
            max(end.toordinal() - 120, date(2015, 1, 1).toordinal())
        )
        try:
            frame = fetch_bse_disclosed_deals_history(kind, start, end)
        except Exception:
            if kind == "block":
                try:
                    frame = _fetch_bse_beta_block_deals_frame()
                except Exception as exc:
                    raise DisclosedDealsFetchError(
                        f"Failed to fetch BSE {kind} deals: {exc}"
                    ) from exc
            else:
                raise DisclosedDealsFetchError(
                    f"Failed to fetch BSE historical {kind} deals"
                )

    try:
        all_deals = normalize_disclosed_deals_frame(frame, kind=kind)
    except DisclosedDealsFetchError:
        raise
    except Exception as exc:
        raise DisclosedDealsFetchError(f"Failed to parse {kind} deals: {exc}") from exc

    if session is not None:
        all_deals = enrich_with_portfolio(all_deals, session)

    available = tuple(
        sorted({d.deal_date for d in all_deals if d.deal_date is not None}, reverse=True)
    )
    portfolio_dates = tuple(
        sorted(
            {d.deal_date for d in all_deals if d.deal_date is not None and d.in_portfolio},
            reverse=True,
        )
    )
    if as_of_date is not None:
        target = as_of_date
    elif available:
        target = available[0]
    else:
        target = today

    deals = [d for d in all_deals if d.deal_date == target]
    deals = flag_arbitrage_deals(deals)
    if fetch_frame is None:
        deals = enrich_with_market_caps(deals)
    deals = sorted(
        deals,
        key=lambda d: (
            (d.scrip_name or "").casefold(),
            d.bse_code,
            (d.client_name or "").casefold(),
            d.deal_type,
        ),
    )

    return DisclosedDealsResult(
        as_of_date=target,
        fetched_at=datetime.now(timezone.utc),
        deals=deals,
        available_dates=available,
        portfolio_dates=portfolio_dates,
        kind=kind,
    )
