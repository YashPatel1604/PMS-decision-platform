"""BSE annual filing XBRL fetcher for balance-sheet / quality metrics (Flag=1)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from xml.etree import ElementTree as ET

import httpx

from pms_platform.market_data.bse_http import bse_headers

_BSE_XBRL_DETAILS_URL = "https://api.bseindia.com/BseIndiaAPI/api/GetCorXbrlDetails_ng/w"
_ANNUAL_FLAG = 1
_INR_TO_CRORE = Decimal("10000000")
_MAX_RETRIES = 3
_RETRY_BACKOFF_SEC = 1.5


class BseAnnualXbrlFetchError(RuntimeError):
    """Raised when annual XBRL fetch or parse fails."""


@dataclass(frozen=True)
class BseAnnualFundamentals:
    """Balance-sheet and quality metrics parsed from annual XBRL filing."""

    bse_code: str
    fiscal_year: int
    period_end_date: date

    total_assets: Decimal | None
    total_equity: Decimal | None
    total_debt: Decimal | None
    cash_and_equivalents: Decimal | None
    finance_costs: Decimal | None
    current_assets: Decimal | None
    current_liabilities: Decimal | None
    shares_outstanding: Decimal | None
    sales: Decimal | None
    pat: Decimal | None

    # Derived ratios (computed during parse)
    roce: Decimal | None
    roe: Decimal | None
    roa: Decimal | None
    debt_to_equity: Decimal | None
    interest_coverage: Decimal | None
    current_ratio: Decimal | None


def _local_tag(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _parse_dec(value: object) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text or text in {"--", "-", "—", "na", "n/a"}:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _to_crores(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return (value / _INR_TO_CRORE).quantize(Decimal("0.01"))


def _divide(num: Decimal | None, den: Decimal | None) -> Decimal | None:
    if num is None or den is None or den == 0:
        return None
    return (num / den).quantize(Decimal("0.0001"))


# XBRL tag aliases for each balance-sheet concept.
_TAGS: dict[str, list[str]] = {
    "total_assets": [
        "Assets",
        "TotalAssets",
        "in-bse-fin:Assets",
        "in-ind-as-fin:Assets",
    ],
    "total_equity": [
        "Equity",
        "TotalEquity",
        "ShareholdersEquity",
        "EquityShareholdersEquity",
        "in-bse-fin:Equity",
        "in-ind-as-fin:Equity",
    ],
    "total_debt": [
        "LongTermBorrowings",
        "ShortTermBorrowings",
        "TotalBorrowings",
        "Borrowings",
        "in-bse-fin:Borrowings",
        "in-ind-as-fin:Borrowings",
    ],
    "cash_and_equivalents": [
        "CashAndCashEquivalents",
        "CashAndBankBalances",
        "in-bse-fin:CashAndCashEquivalents",
        "in-ind-as-fin:CashAndCashEquivalents",
    ],
    "finance_costs": [
        "FinanceCosts",
        "InterestExpense",
        "FinanceCharges",
        "in-bse-fin:FinanceCosts",
        "in-ind-as-fin:FinanceCosts",
    ],
    "current_assets": [
        "CurrentAssets",
        "TotalCurrentAssets",
        "in-bse-fin:CurrentAssets",
        "in-ind-as-fin:CurrentAssets",
    ],
    "current_liabilities": [
        "CurrentLiabilities",
        "TotalCurrentLiabilities",
        "in-bse-fin:CurrentLiabilities",
        "in-ind-as-fin:CurrentLiabilities",
    ],
    "shares_outstanding": [
        "EquityShareCapital",
        "PaidUpCapital",
        "in-bse-fin:EquityShareCapital",
        "in-ind-as-fin:EquityShareCapital",
    ],
    "ebit": [
        "ProfitBeforeExceptionalAndExtraordinaryItemsAndTax",
        "ProfitBeforeTax",
        "EarningsBeforeInterestAndTax",
        "in-bse-fin:ProfitBeforeExceptionalItemsAndTax",
        "in-ind-as-fin:ProfitBeforeExceptionalItemsAndTax",
    ],
    "pat": [
        "ProfitForThePeriod",
        "ProfitForThePeriodFromContinuingOperations",
        "ProfitAfterTax",
        "in-bse-fin:ProfitForThePeriod",
        "in-ind-as-fin:ProfitForThePeriod",
    ],
    "sales": [
        "RevenueFromOperations",
        "Revenue",
        "in-bse-fin:RevenueFromOperations",
        "in-ind-as-fin:RevenueFromOperations",
    ],
}


def _extract_xbrl_values(root: ET.Element) -> dict[str, Decimal | None]:
    """Walk an XBRL XML tree and extract tagged values as a dict keyed by concept."""
    tag_to_concept: dict[str, str] = {}
    for concept, aliases in _TAGS.items():
        for alias in aliases:
            local = alias.split(":")[-1]
            tag_to_concept[local.lower()] = concept

    # Find the context covering the full-year period (not interim).
    # For annual XBRL, we look for the context with the widest date range.
    contexts: dict[str, tuple[date | None, date | None]] = {}
    for elem in root.iter():
        local = _local_tag(elem.tag)
        if local == "context":
            ctx_id = elem.get("id", "")
            start_date: date | None = None
            end_date: date | None = None
            for child in elem:
                child_local = _local_tag(child.tag)
                if child_local == "period":
                    for period_child in child:
                        pc_local = _local_tag(period_child.tag)
                        if pc_local == "startDate" and period_child.text:
                            try:
                                start_date = date.fromisoformat(period_child.text.strip())
                            except ValueError:
                                pass
                        elif pc_local == "endDate" and period_child.text:
                            try:
                                end_date = date.fromisoformat(period_child.text.strip())
                            except ValueError:
                                pass
            contexts[ctx_id] = (start_date, end_date)

    # Pick the annual context (longest duration, ~365 days).
    annual_ctx: str | None = None
    max_duration = 0
    for ctx_id, (start, end) in contexts.items():
        if start and end:
            duration = (end - start).days
            if duration > max_duration:
                max_duration = duration
                annual_ctx = ctx_id
                annual_end = end

    values: dict[str, list[Decimal]] = {k: [] for k in _TAGS}

    for elem in root.iter():
        local = _local_tag(elem.tag).lower()
        concept = tag_to_concept.get(local)
        if concept is None:
            continue
        ctx_ref = elem.get("contextRef", "")
        if annual_ctx and ctx_ref != annual_ctx:
            continue
        d = _parse_dec(elem.text)
        if d is not None:
            values[concept].append(d)

    # Take the last value if multiple matches (most specific).
    return {k: v[-1] if v else None for k, v in values.items()}


def parse_annual_xbrl(bse_code: str, xml_text: str, fiscal_year: int, period_end_date: date) -> BseAnnualFundamentals | None:
    """Parse an annual XBRL XML string into BseAnnualFundamentals."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None

    v = _extract_xbrl_values(root)

    total_assets = _to_crores(v.get("total_assets"))
    total_equity = _to_crores(v.get("total_equity"))
    total_debt = _to_crores(v.get("total_debt"))
    cash = _to_crores(v.get("cash_and_equivalents"))
    finance_costs = _to_crores(v.get("finance_costs"))
    current_assets = _to_crores(v.get("current_assets"))
    current_liabilities = _to_crores(v.get("current_liabilities"))
    shares = v.get("shares_outstanding")
    pat = _to_crores(v.get("pat"))
    sales = _to_crores(v.get("sales"))
    ebit = _to_crores(v.get("ebit"))

    # Capital Employed = Total Assets − Current Liabilities.
    capital_employed: Decimal | None = None
    if total_assets and current_liabilities:
        capital_employed = total_assets - current_liabilities

    roce = _divide(ebit, capital_employed)
    if roce:
        roce = (roce * 100).quantize(Decimal("0.0001"))

    roe = _divide(pat, total_equity)
    if roe:
        roe = (roe * 100).quantize(Decimal("0.0001"))

    roa = _divide(pat, total_assets)
    if roa:
        roa = (roa * 100).quantize(Decimal("0.0001"))

    debt_to_equity = _divide(total_debt, total_equity)
    interest_coverage = _divide(ebit, finance_costs)
    current_ratio = _divide(current_assets, current_liabilities)

    return BseAnnualFundamentals(
        bse_code=bse_code,
        fiscal_year=fiscal_year,
        period_end_date=period_end_date,
        total_assets=total_assets,
        total_equity=total_equity,
        total_debt=total_debt,
        cash_and_equivalents=cash,
        finance_costs=finance_costs,
        current_assets=current_assets,
        current_liabilities=current_liabilities,
        shares_outstanding=shares,
        sales=sales,
        pat=pat,
        roce=roce,
        roe=roe,
        roa=roa,
        debt_to_equity=debt_to_equity,
        interest_coverage=interest_coverage,
        current_ratio=current_ratio,
    )


def _list_annual_filings(
    client: httpx.Client,
    bse_code: str,
    *,
    timeout: float,
    years_back: int = 3,
) -> list[dict[str, Any]]:
    """List annual XBRL filings for a BSE code (requires fromdate/todate)."""
    to_date = date.today()
    from_date = to_date - timedelta(days=max(years_back, 1) * 366)
    params = {
        "scripcode": bse_code,
        "flag": _ANNUAL_FLAG,
        "fromdate": from_date.strftime("%Y/%m/%d"),
        "todate": to_date.strftime("%Y/%m/%d"),
    }
    for attempt in range(_MAX_RETRIES):
        try:
            resp = client.get(
                _BSE_XBRL_DETAILS_URL,
                params=params,
                timeout=timeout,
            )
            if resp.status_code != 200 or "json" not in resp.headers.get("content-type", "").lower():
                time.sleep(_RETRY_BACKOFF_SEC * (attempt + 1))
                continue
            payload = resp.json()
            rows = payload.get("Table") if isinstance(payload, dict) else None
            if isinstance(rows, list) and rows:
                return [r for r in rows if isinstance(r, dict)]
        except Exception:
            time.sleep(_RETRY_BACKOFF_SEC * (attempt + 1))
    return []


def _fetch_xml(client: httpx.Client, url: str, *, timeout: float) -> str | None:
    """Download an XBRL XML document."""
    for attempt in range(_MAX_RETRIES):
        try:
            resp = client.get(url, timeout=timeout)
            if resp.status_code == 200 and len(resp.content) > 200:
                return resp.text
        except Exception:
            pass
        time.sleep(_RETRY_BACKOFF_SEC * (attempt + 1))
    return None


def _fiscal_year_from_date(d: date) -> int:
    """Indian fiscal year ends in March; Apr 2024–Mar 2025 is FY2025."""
    return d.year + 1 if d.month > 3 else d.year


def fetch_bse_annual_fundamentals(
    bse_code: str,
    *,
    years_back: int = 3,
    timeout: float = 30.0,
    client: httpx.Client | None = None,
) -> list[BseAnnualFundamentals]:
    """Fetch and parse annual XBRL filings for a BSE scrip."""

    def _do_fetch(c: httpx.Client) -> list[BseAnnualFundamentals]:
        try:
            c.get("https://www.bseindia.com/")
        except Exception:
            pass

        filings = _list_annual_filings(c, bse_code, timeout=timeout, years_back=years_back)
        if not filings:
            return []

        cutoff_year = date.today().year - years_back
        results: list[BseAnnualFundamentals] = []
        seen_years: set[int] = set()

        for filing in filings:
            xbrl_url = str(
                filing.get("XBRL")
                or filing.get("XbrlFile")
                or filing.get("xbrlurl")
                or ""
            ).strip()
            # BSE annual Ind-AS balance-sheet filings (classic path).
            if not xbrl_url or "Main_Ind_As" not in xbrl_url:
                continue

            date_raw = str(
                filing.get("ATTACHMENT_DATE")
                or filing.get("AttachmentDate")
                or filing.get("attachmentdate")
                or filing.get("xbrldate")
                or ""
            ).strip()
            period_end: date | None = None
            if date_raw and date_raw not in {"-", "—"}:
                try:
                    dt = datetime.fromisoformat(date_raw.replace("Z", "+00:00"))
                    period_end = dt.date()
                except ValueError:
                    pass
            if period_end is None:
                continue

            fy = _fiscal_year_from_date(period_end)
            if fy < cutoff_year or fy in seen_years:
                continue

            if xbrl_url.startswith("/"):
                xbrl_url = f"https://www.bseindia.com{xbrl_url}"

            xml_text = _fetch_xml(c, xbrl_url, timeout=timeout)
            if not xml_text:
                continue

            parsed = parse_annual_xbrl(bse_code, xml_text, fy, period_end)
            if parsed is not None:
                results.append(parsed)
                seen_years.add(fy)

            time.sleep(0.3)

        return results

    if client is not None:
        return _do_fetch(client)
    headers = bse_headers(referer="https://www.bseindia.com/corporates/xbrl.aspx")
    with httpx.Client(headers=headers, follow_redirects=True, timeout=timeout) as c:
        return _do_fetch(c)
