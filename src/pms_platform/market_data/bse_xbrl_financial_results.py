"""BSE financial-results XBRL backfill (GetCorXbrlDetails_ng, Flag=22)."""

from __future__ import annotations

import calendar
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from xml.etree import ElementTree as ET

import httpx

from pms_platform.market_data.bse_financial_results import BseQuarterlyResult, fiscal_label

_BSE_API = "https://api.bseindia.com/BseIndiaAPI/api"
_XBRL_DETAILS_URL = f"{_BSE_API}/GetCorXbrlDetails_ng/w"
_FINANCIAL_RESULTS_FLAG = 22
_INR_TO_CRORE = Decimal("10000000")
_MAX_RETRIES = 3
_RETRY_BACKOFF_SEC = 1.5


class BseXbrlFinancialResultsFetchError(RuntimeError):
    """Raised when BSE XBRL financial-results fetch or parse fails."""


@dataclass(frozen=True)
class BseXbrlFiling:
    """One BSE financial-results XBRL filing row."""

    bse_code: str
    attachment_date: datetime | None
    xbrl_url: str
    xbrl_date: datetime | None


def _bse_headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.bseindia.com/corporates/xbrl.aspx",
    }


def _local_tag(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _parse_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text or text in {"--", "-", "—", "na", "n/a"}:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _parse_iso_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _period_label(period_end: date) -> str:
    month = calendar.month_abbr[period_end.month]
    return f"{month}-{period_end.strftime('%y')}"


def _bse_date_param(value: date) -> str:
    return value.strftime("%Y/%m/%d")


def _to_crores(value_inr: Decimal | None) -> Decimal | None:
    if value_inr is None:
        return None
    return (value_inr / _INR_TO_CRORE).quantize(Decimal("0.01"))


def _margin_pct(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return ((numerator / denominator) * Decimal("100")).quantize(Decimal("0.01"))


def list_financial_result_xbrl_filings(
    bse_code: str,
    *,
    from_date: date,
    to_date: date,
    timeout: float = 30.0,
    client: httpx.Client | None = None,
) -> tuple[BseXbrlFiling, ...]:
    """List BSE financial-results XBRL filings for one scrip in a date window."""
    code = bse_code.strip()
    if not code:
        raise BseXbrlFinancialResultsFetchError("BSE code is required")

    params = {
        "Flag": _FINANCIAL_RESULTS_FLAG,
        "scripcode": code,
        "fromdate": _bse_date_param(from_date),
        "todate": _bse_date_param(to_date),
    }

    def _fetch(existing: httpx.Client) -> list[dict[str, Any]]:
        response = existing.get(_XBRL_DETAILS_URL, params=params, timeout=timeout)
        response.raise_for_status()
        payload: Any = response.json()
        rows = payload.get("Table") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict)]

    if client is not None:
        rows = _fetch(client)
    else:
        with httpx.Client(
            headers=_bse_headers(),
            timeout=timeout,
            follow_redirects=True,
        ) as owned:
            try:
                owned.get("https://www.bseindia.com/", timeout=timeout)
            except Exception:
                pass
            rows = _fetch(owned)

    filings: list[BseXbrlFiling] = []
    for row in rows:
        xbrl_url = str(row.get("xbrlurl") or "").strip()
        if not xbrl_url:
            continue
        filings.append(
            BseXbrlFiling(
                bse_code=code,
                attachment_date=_parse_iso_datetime(row.get("attachmentdate")),
                xbrl_url=xbrl_url,
                xbrl_date=_parse_iso_datetime(row.get("xbrldate")),
            )
        )

    filings.sort(
        key=lambda row: row.xbrl_date or row.attachment_date or datetime.min,
        reverse=True,
    )
    return tuple(filings)


def parse_xbrl_quarterly_result(payload: bytes | str) -> BseQuarterlyResult | None:
    """Parse one BSE financial-results XBRL document into a quarterly row."""
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise BseXbrlFinancialResultsFetchError(f"Invalid XBRL XML: {exc}") from exc

    contexts: dict[str, dict[str, Any]] = {}
    for element in root.iter():
        if _local_tag(element.tag) != "context":
            continue
        context_id = element.attrib.get("id")
        if not context_id:
            continue
        start_date: date | None = None
        end_date: date | None = None
        has_scenario = False
        for child in element.iter():
            tag = _local_tag(child.tag)
            if tag == "startDate" and child.text:
                start_date = date.fromisoformat(child.text.strip())
            elif tag == "endDate" and child.text:
                end_date = date.fromisoformat(child.text.strip())
            elif tag == "scenario":
                has_scenario = True
        if start_date is None or end_date is None:
            continue
        contexts[context_id] = {
            "start": start_date,
            "end": end_date,
            "has_scenario": has_scenario,
        }

    quarter_context_id = _select_quarter_context(contexts)
    if quarter_context_id is None:
        return None

    period_end = contexts[quarter_context_id]["end"]
    metrics = _extract_metrics(root, quarter_context_id)
    sales = _to_crores(metrics.get("RevenueFromOperations"))
    pat = _to_crores(metrics.get("ProfitLossForPeriod"))
    if sales is None and pat is None:
        return None

    revenue_inr = metrics.get("RevenueFromOperations")
    pbt_inr = metrics.get("ProfitBeforeExceptionalItemsAndTax")
    finance_inr = metrics.get("FinanceCosts") or Decimal("0")
    other_income_inr = metrics.get("OtherIncome") or Decimal("0")
    operating_inr = None
    if pbt_inr is not None:
        operating_inr = pbt_inr + finance_inr - other_income_inr
    opm = _margin_pct(operating_inr, revenue_inr)
    npm = _margin_pct(metrics.get("ProfitLossForPeriod"), revenue_inr)

    fiscal_year, fiscal_quarter = fiscal_label(period_end)
    return BseQuarterlyResult(
        period_label=_period_label(period_end),
        period_end_date=period_end,
        fiscal_year=fiscal_year,
        fiscal_quarter=fiscal_quarter,
        sales=sales,
        pat=pat,
        opm=opm,
        npm=npm,
    )


def _select_quarter_context(contexts: dict[str, dict[str, Any]]) -> str | None:
    candidates: list[tuple[date, str]] = []
    for context_id, meta in contexts.items():
        if meta["has_scenario"]:
            continue
        days = (meta["end"] - meta["start"]).days + 1
        if 80 <= days <= 100:
            candidates.append((meta["end"], context_id))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _extract_metrics(root: ET.Element, context_id: str) -> dict[str, Decimal]:
    wanted = {
        "RevenueFromOperations",
        "OtherIncome",
        "ProfitBeforeExceptionalItemsAndTax",
        "FinanceCosts",
        "ProfitLossForPeriod",
    }
    metrics: dict[str, Decimal] = {}
    for element in root.iter():
        name = _local_tag(element.tag)
        if name not in wanted:
            continue
        if element.attrib.get("contextRef") != context_id:
            continue
        value = _parse_decimal(element.text)
        if value is not None:
            metrics[name] = value
    return metrics


def fetch_xbrl_quarterly_results(
    bse_code: str,
    *,
    years_back: int = 3,
    max_quarters: int = 8,
    timeout: float = 30.0,
    client: httpx.Client | None = None,
) -> tuple[BseQuarterlyResult, ...]:
    """Backfill quarterly metrics from BSE financial-results XBRL filings."""
    code = bse_code.strip()
    if not code:
        raise BseXbrlFinancialResultsFetchError("BSE code is required")

    to_date = date.today()
    from_date = to_date - timedelta(days=max(years_back, 1) * 366)
    last_error: Exception | None = None

    for attempt in range(_MAX_RETRIES):
        try:
            if client is not None:
                return _fetch_xbrl_quarters(
                    client,
                    code,
                    from_date=from_date,
                    to_date=to_date,
                    max_quarters=max_quarters,
                    timeout=timeout,
                )
            with httpx.Client(
                headers=_bse_headers(),
                timeout=timeout,
                follow_redirects=True,
            ) as owned:
                try:
                    owned.get("https://www.bseindia.com/", timeout=timeout)
                except Exception:
                    pass
                return _fetch_xbrl_quarters(
                    owned,
                    code,
                    from_date=from_date,
                    to_date=to_date,
                    max_quarters=max_quarters,
                    timeout=timeout,
                )
        except Exception as exc:
            last_error = exc
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_BACKOFF_SEC * (attempt + 1))

    raise BseXbrlFinancialResultsFetchError(
        f"BSE XBRL financial results fetch failed for {code}: {last_error}"
    )


def _fetch_xbrl_quarters(
    client: httpx.Client,
    bse_code: str,
    *,
    from_date: date,
    to_date: date,
    max_quarters: int,
    timeout: float,
) -> tuple[BseQuarterlyResult, ...]:
    filings = list_financial_result_xbrl_filings(
        bse_code,
        from_date=from_date,
        to_date=to_date,
        timeout=timeout,
        client=client,
    )
    by_period: dict[date, BseQuarterlyResult] = {}
    seen_urls: set[str] = set()

    for filing in filings:
        if max_quarters > 0 and len(by_period) >= max_quarters:
            break
        if filing.xbrl_url in seen_urls:
            continue
        seen_urls.add(filing.xbrl_url)
        url = filing.xbrl_url
        if url.startswith("/"):
            url = f"https://www.bseindia.com{url}"
        response = client.get(url, timeout=timeout)
        if response.status_code != 200 or not response.content.strip():
            continue
        quarter = parse_xbrl_quarterly_result(response.content)
        if quarter is None:
            continue
        existing = by_period.get(quarter.period_end_date)
        if existing is None:
            by_period[quarter.period_end_date] = quarter

    quarters = sorted(by_period.values(), key=lambda row: row.period_end_date)
    if max_quarters > 0:
        quarters = quarters[-max_quarters:]
    return tuple(quarters)


def merge_quarterly_results(
    *sources: tuple[BseQuarterlyResult, ...],
) -> tuple[BseQuarterlyResult, ...]:
    """Merge quarter rows; earlier sources win on duplicate period_end_date."""
    merged: dict[date, BseQuarterlyResult] = {}
    for source in reversed(sources):
        for quarter in source:
            merged[quarter.period_end_date] = quarter
    return tuple(sorted(merged.values(), key=lambda row: row.period_end_date))


def fetch_bse_quarterly_results_with_history(
    bse_code: str,
    *,
    max_quarters: int = 8,
    years_back: int = 2,
    timeout: float = 30.0,
    client: httpx.Client | None = None,
    skip_integrated_if_tabresults: int = 2,
):
    """Fetch TabResults snapshot plus XBRL/Integrated-Finance backfill."""
    from pms_platform.market_data.bse_financial_results import (
        BseResultsSnapshot,
        fetch_bse_results_snapshot,
    )
    from pms_platform.market_data.bse_integrated_finance import (
        BseIntegratedFinanceFetchError,
        fetch_integrated_finance_quarters,
    )

    snapshot = fetch_bse_results_snapshot(bse_code, timeout=timeout, client=client)
    try:
        historical = fetch_xbrl_quarterly_results(
            bse_code,
            years_back=years_back,
            max_quarters=max_quarters,
            timeout=timeout,
            client=client,
        )
    except BseXbrlFinancialResultsFetchError:
        historical = ()

    integrated: tuple = ()
    tab_count = len(snapshot.quarters)
    if tab_count < skip_integrated_if_tabresults:
        try:
            integrated = fetch_integrated_finance_quarters(
                bse_code,
                max_quarters=min(max_quarters, 4),
                timeout=timeout,
                client=client,
            )
        except BseIntegratedFinanceFetchError:
            integrated = ()

    # TabResults wins on overlap; integrated fills the 2025+ HTML gap; classic XBRL fills older.
    quarters = merge_quarterly_results(snapshot.quarters, integrated, historical)
    if max_quarters > 0:
        quarters = quarters[-max_quarters:]
    return BseResultsSnapshot(
        bse_code=snapshot.bse_code,
        currency_unit=snapshot.currency_unit,
        quarters=quarters,
    )
