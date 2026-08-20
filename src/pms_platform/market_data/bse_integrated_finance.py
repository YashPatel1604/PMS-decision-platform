"""BSE Integrated Finance iXBRL HTML filings (fills post-2024 TabResults gaps)."""

from __future__ import annotations

import calendar
import re
import time
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from pms_platform.market_data.bse_financial_results import BseQuarterlyResult, fiscal_label
from pms_platform.market_data.bse_http import bse_headers

_BSE_API = "https://api.bseindia.com/BseIndiaAPI/api"
_FINANCE_RESULT_URL = f"{_BSE_API}/Corp_FinanceResult_ng_new/w"
_XBRL_FILES = "https://www.bseindia.com/XBRLFILES"
_MAX_RETRIES = 3
_RETRY_BACKOFF_SEC = 1.0
_STANDALONE_SCAN_WINDOW = 5
_QUARTER_CODE_RE = re.compile(r"^(JQ|SQ|DQ|MQ)(\d{4})-(\d{4})$")

_NONFRAC_RE = re.compile(
    r"<ix:nonFraction\b([^>]*)>([^<]*)</ix:nonFraction>",
    re.IGNORECASE,
)
_NONNUM_RE = re.compile(
    r"<ix:nonNumeric\b([^>]*)>([^<]*)</ix:nonNumeric>",
    re.IGNORECASE,
)
_ATTR_RE = re.compile(r"""([A-Za-z_:]+)\s*=\s*['"]([^'"]*)['"]""")
_CONTEXT_RE = re.compile(
    r"""<xbrli:context\b[^>]*\bid=['"]([^'"]+)['"][^>]*>(.*?)</xbrli:context>""",
    re.IGNORECASE | re.DOTALL,
)
_START_RE = re.compile(r"<xbrli:startDate>([^<]+)</xbrli:startDate>", re.IGNORECASE)
_END_RE = re.compile(r"<xbrli:endDate>([^<]+)</xbrli:endDate>", re.IGNORECASE)
_SCENARIO_RE = re.compile(r"<xbrli:scenario\b", re.IGNORECASE)


class BseIntegratedFinanceFetchError(RuntimeError):
    """Raised when BSE integrated-finance fetch fails."""


def _bse_headers() -> dict[str, str]:
    return bse_headers(referer="https://www.bseindia.com/corporates/results.aspx")


def _parse_decimal(text: str) -> Decimal | None:
    cleaned = str(text or "").strip().replace(",", "")
    if not cleaned or cleaned in {"--", "-", "—", "na", "n/a"}:
        return None
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _attrs(blob: str) -> dict[str, str]:
    return {key.casefold(): value for key, value in _ATTR_RE.findall(blob)}


def _local_name(value: str) -> str:
    return value.split(":")[-1]


def _period_label(period_end: date) -> str:
    return f"{calendar.month_abbr[period_end.month]}-{period_end.strftime('%y')}"


def _to_crores(value: Decimal | None, *, rounding: str) -> Decimal | None:
    if value is None:
        return None
    norm = rounding.casefold()
    if "lakh" in norm:
        return (value / Decimal("100")).quantize(Decimal("0.01"))
    if "thousand" in norm:
        return (value / Decimal("10000")).quantize(Decimal("0.01"))
    # Default: already crores (or absolute display treated as crores by BSE UI).
    return value.quantize(Decimal("0.01"))


def _margin_pct(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return ((numerator / denominator) * Decimal("100")).quantize(Decimal("0.01"))


def _html_url_from_xml_name(xml_name: str) -> str | None:
    text = (xml_name or "").strip()
    if not text:
        return None
    if text.startswith("http"):
        if text.endswith(".html"):
            return text
        if text.endswith(".xml"):
            stem = text.rsplit("/", 1)[-1].removesuffix(".xml")
            return f"{_XBRL_FILES}/IFIndasDuplicateUploadDocument/{stem}_IFIndAs.html"
        return text
    if text.endswith(".html"):
        return f"{_XBRL_FILES}/{text.lstrip('/')}"
    if text.endswith(".xml"):
        stem = text.rsplit("/", 1)[-1].removesuffix(".xml")
        return f"{_XBRL_FILES}/IFIndasDuplicateUploadDocument/{stem}_IFIndAs.html"
    return None


def _nearby_html_urls(url: str, *, window: int = _STANDALONE_SCAN_WINDOW) -> list[str]:
    match = re.search(r"^(.*?Integrated_Finance_Ind_As_\d+_)(\d+)(_IFIndAs\.html)$", url)
    if not match:
        return [url]
    prefix, number, suffix = match.group(1), int(match.group(2)), match.group(3)
    urls = [url]
    for delta in range(1, window + 1):
        urls.append(f"{prefix}{number - delta}{suffix}")
    return urls


def parse_integrated_finance_html(payload: bytes | str) -> BseQuarterlyResult | None:
    """Parse one BSE Integrated Finance iXBRL HTML document into a quarter row."""
    text = payload.decode("utf-8", errors="ignore") if isinstance(payload, bytes) else payload
    if "ix:nonFraction" not in text and "ix:nonfraction" not in text.casefold():
        return None

    contexts: dict[str, dict[str, Any]] = {}
    for context_id, body in _CONTEXT_RE.findall(text):
        start_match = _START_RE.search(body)
        end_match = _END_RE.search(body)
        if not start_match or not end_match:
            continue
        try:
            start = date.fromisoformat(start_match.group(1).strip())
            end = date.fromisoformat(end_match.group(1).strip())
        except ValueError:
            continue
        contexts[context_id] = {
            "start": start,
            "end": end,
            "has_scenario": bool(_SCENARIO_RE.search(body)),
        }

    quarter_context = _select_quarter_context(contexts)
    if quarter_context is None:
        return None

    meta: dict[str, str] = {}
    for attr_blob, value in _NONNUM_RE.findall(text):
        attrs = _attrs(attr_blob)
        name = _local_name(attrs.get("name", ""))
        if name:
            meta[name] = value.strip()

    nature = meta.get("NatureOfReportStandaloneConsolidated", "")
    # Prefer standalone when available; still accept consolidated if that's all we have.
    facts: dict[str, Decimal] = {}
    for attr_blob, value in _NONFRAC_RE.findall(text):
        attrs = _attrs(attr_blob)
        if attrs.get("contextref") != quarter_context:
            continue
        name = _local_name(attrs.get("name", ""))
        parsed = _parse_decimal(value)
        if name and parsed is not None:
            facts[name] = parsed

    rounding = meta.get("LevelOfRounding", "Crores")
    sales = _to_crores(facts.get("RevenueFromOperations"), rounding=rounding)
    pat = _to_crores(facts.get("ProfitLossForPeriod"), rounding=rounding)
    if sales is None and pat is None:
        return None

    revenue = _to_crores(facts.get("RevenueFromOperations"), rounding=rounding)
    pbt = _to_crores(facts.get("ProfitBeforeExceptionalItemsAndTax"), rounding=rounding)
    finance = _to_crores(facts.get("FinanceCosts"), rounding=rounding) or Decimal("0")
    other_income = _to_crores(facts.get("OtherIncome"), rounding=rounding) or Decimal("0")
    operating = None
    if pbt is not None:
        operating = pbt + finance - other_income
    opm = _margin_pct(operating, revenue)
    npm = _margin_pct(pat, revenue)

    period_end = contexts[quarter_context]["end"]
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


def _list_finance_result_rows(
    client: httpx.Client,
    bse_code: str,
    *,
    timeout: float,
) -> list[dict[str, Any]]:
    param_sets = [
        {"SCRIP_CD": bse_code, "FlagDur": "7", "HFQ": "4", "ISUBGROUP_CODE": "", "segment": "C"},
        {"SCRIP_CD": bse_code, "FlagDur": "7", "HFQ": "5", "ISUBGROUP_CODE": "", "segment": "C"},
        {"SCRIP_CD": bse_code, "FlagDur": "7", "HFQ": "6", "ISUBGROUP_CODE": "", "segment": "C"},
        {"SCRIP_CD": bse_code, "FlagDur": "1", "HFQ": "4", "ISUBGROUP_CODE": "", "segment": "C"},
    ]
    for params in param_sets:
        for attempt in range(_MAX_RETRIES):
            try:
                response = client.get(_FINANCE_RESULT_URL, params=params, timeout=timeout)
                if response.status_code != 200 or len(response.content) <= 50:
                    time.sleep(_RETRY_BACKOFF_SEC * (attempt + 1))
                    continue
                if "Access Denied" in response.text[:200]:
                    time.sleep(_RETRY_BACKOFF_SEC * (attempt + 1))
                    continue
                payload: Any = response.json()
                rows = payload.get("Table") if isinstance(payload, dict) else None
                if isinstance(rows, list) and rows:
                    return [row for row in rows if isinstance(row, dict)]
            except Exception:
                time.sleep(_RETRY_BACKOFF_SEC * (attempt + 1))
    return []


def _fetch_html_document(
    client: httpx.Client,
    url: str,
    *,
    timeout: float,
) -> tuple[str, bytes] | None:
    response = client.get(url, timeout=timeout)
    if response.status_code != 200 or len(response.content) < 1000:
        return None
    if b"ix:nonFraction" not in response.content and b"ix:nonfraction" not in response.content.lower():
        return None
    return url, response.content


def _period_end_from_quarter_code(quarter_code: str) -> date | None:
    match = _QUARTER_CODE_RE.match((quarter_code or "").strip().upper())
    if not match:
        return None
    kind = match.group(1)
    start_year = int(match.group(2))
    if kind == "JQ":
        return date(start_year, 6, 30)
    if kind == "SQ":
        return date(start_year, 9, 30)
    if kind == "DQ":
        return date(start_year, 12, 31)
    # MQ = March quarter of fiscal year ending match.group(3)
    end_year = int(match.group(3))
    return date(end_year, 3, 31)


def _prefer_standalone_html(
    client: httpx.Client,
    seed_url: str,
    *,
    timeout: float,
) -> tuple[str, bytes, BseQuarterlyResult] | None:
    consolidated: tuple[str, bytes, BseQuarterlyResult] | None = None

    for url in _nearby_html_urls(seed_url):
        fetched = _fetch_html_document(client, url, timeout=timeout)
        if fetched is None:
            continue
        resolved_url, content = fetched
        text = content.decode("utf-8", errors="ignore")
        nature = None
        for attr_blob, value in _NONNUM_RE.findall(text):
            attrs = _attrs(attr_blob)
            if _local_name(attrs.get("name", "")) == "NatureOfReportStandaloneConsolidated":
                nature = value.strip()
                break
        quarter = parse_integrated_finance_html(content)
        if quarter is None:
            continue
        if nature and nature.casefold() == "standalone":
            return resolved_url, content, quarter
        if consolidated is None:
            consolidated = (resolved_url, content, quarter)

    return consolidated


def fetch_integrated_finance_quarters(
    bse_code: str,
    *,
    max_quarters: int = 12,
    timeout: float = 30.0,
    client: httpx.Client | None = None,
) -> tuple[BseQuarterlyResult, ...]:
    """Backfill quarterly metrics from BSE Integrated Finance HTML filings."""
    code = bse_code.strip()
    if not code:
        raise BseIntegratedFinanceFetchError("BSE code is required")

    def _run(existing: httpx.Client) -> tuple[BseQuarterlyResult, ...]:
        try:
            existing.get("https://www.bseindia.com/")
            existing.get(
                "https://www.bseindia.com/corporates/results.aspx",
                params={"Code": code},
            )
        except Exception:
            pass
        rows = _list_finance_result_rows(existing, code, timeout=timeout)
        by_period: dict[date, BseQuarterlyResult] = {}

        # One seed per quarter-code period; skip annual/half-year codes.
        seeds_by_period: dict[date, str] = {}
        for row in rows:
            period_end = _period_end_from_quarter_code(str(row.get("quarter_code") or ""))
            if period_end is None or period_end in seeds_by_period:
                continue
            seed = None
            for key in ("XMLName", "Consol_XMLName"):
                seed = _html_url_from_xml_name(str(row.get(key) or ""))
                if seed:
                    break
            if seed:
                seeds_by_period[period_end] = seed

        for period_hint, seed in sorted(seeds_by_period.items(), reverse=True):
            if period_hint in by_period:
                continue
            if max_quarters > 0 and len(by_period) >= max_quarters:
                break
            preferred = _prefer_standalone_html(existing, seed, timeout=timeout)
            if preferred is None:
                continue
            _url, _content, quarter = preferred
            by_period.setdefault(quarter.period_end_date, quarter)

        quarters = sorted(by_period.values(), key=lambda row: row.period_end_date)
        if max_quarters > 0:
            quarters = quarters[-max_quarters:]
        return tuple(quarters)

    if client is not None:
        return _run(client)
    with httpx.Client(headers=_bse_headers(), timeout=timeout, follow_redirects=True) as owned:
        return _run(owned)
