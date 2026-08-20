"""BSE quarterly financial results (TabResults_PAR API)."""

from __future__ import annotations

import calendar
import re
import time
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from pms_platform.market_data.bse_http import bse_headers as _bse_headers

_BSE_API = "https://api.bseindia.com/BseIndiaAPI/api"
_RESULTS_URL = f"{_BSE_API}/TabResults_PAR/w"
_MAX_RETRIES = 3
_RETRY_BACKOFF_SEC = 1.5

_PERIOD_RE = re.compile(r"^([A-Za-z]{3})-(\d{2})$")
_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

_METRIC_ALIASES: dict[str, tuple[str, ...]] = {
    "sales": ("revenue", "total income", "income from operations"),
    "pat": ("net profit", "profit after tax", "pat"),
    "opm": ("opm %", "opm", "operating profit margin"),
    "npm": ("npm %", "npm", "net profit margin"),
}


class BseFinancialResultsFetchError(RuntimeError):
    """Raised when BSE financial results fetch fails after retries."""


@dataclass(frozen=True)
class BseQuarterlyResult:
    """One quarterly period parsed from BSE results snapshot."""

    period_label: str
    period_end_date: date
    fiscal_year: int
    fiscal_quarter: str
    sales: Decimal | None
    pat: Decimal | None
    opm: Decimal | None
    npm: Decimal | None


@dataclass(frozen=True)
class BseResultsSnapshot:
    """Parsed BSE TabResults_PAR response for one scrip."""

    bse_code: str
    currency_unit: str
    quarters: tuple[BseQuarterlyResult, ...]


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


def _norm_title(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").casefold()).strip()


def _metric_key(title: str) -> str | None:
    norm = _norm_title(title)
    for key, aliases in _METRIC_ALIASES.items():
        if norm in aliases or any(alias in norm for alias in aliases):
            return key
    return None


def _parse_period_label(label: str) -> date | None:
    text = label.strip()
    if not text or text.upper().startswith("FY"):
        return None
    match = _PERIOD_RE.match(text)
    if not match:
        return None
    month = _MONTHS.get(match.group(1).casefold())
    if month is None:
        return None
    year = 2000 + int(match.group(2))
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, last_day)


def fiscal_label(period_end: date) -> tuple[int, str]:
    """Map calendar period end to Indian fiscal year/quarter label."""
    month = period_end.month
    if month in {4, 5, 6}:
        quarter = "Q1"
    elif month in {7, 8, 9}:
        quarter = "Q2"
    elif month in {10, 11, 12}:
        quarter = "Q3"
    else:
        quarter = "Q4"
    fiscal_year = period_end.year if month >= 4 else period_end.year - 1
    return fiscal_year, quarter


def _format_results_table(table: dict[str, Any]) -> dict[str, dict[str, Decimal | None]]:
    """Turn BSE fields/data matrix into {period_label: {metric: value}}."""
    fields = table.get("fields") or []
    rows = table.get("data") or []
    if not fields or len(fields) < 2:
        return {}

    period_labels = [str(label) for label in fields[1:]]
    period_metrics: dict[str, dict[str, Decimal | None]] = {
        label: {} for label in period_labels
    }

    for row in rows:
        if not row:
            continue
        title = str(row[0])
        metric = _metric_key(title)
        if metric is None:
            continue
        for index, label in enumerate(period_labels, start=1):
            if index >= len(row):
                break
            value = _parse_decimal(row[index])
            if value is not None:
                period_metrics[label][metric] = value

    return period_metrics


def parse_results_snapshot(bse_code: str, payload: dict[str, Any]) -> BseResultsSnapshot:
    """Parse raw TabResults_PAR JSON into quarterly rows (crores, quarterly only)."""
    table = payload.get("results_in_crores") or payload.get("resultinCr")
    if isinstance(table, list):
        # Raw API uses resultinCr list; normalize to fields/data shape.
        periods = []
        for i in range(2, 5):
            col_val = str(payload.get(f"col{i}", "")).strip()
            if col_val:
                periods.append(col_val)
        fields = ["title"]
        for period in periods:
            fields.append(period)
        data: list[list[str]] = []
        for item in table:
            if not isinstance(item, dict):
                continue
            row = [str(item.get("title", ""))]
            for i in range(1, 4):
                row.append(str(item.get(f"v{i}", "")))
            data.append(row)
        table = {"fields": fields, "data": data}

    if not isinstance(table, dict):
        table = {}

    period_metrics = _format_results_table(table)
    quarters: list[BseQuarterlyResult] = []
    for label, metrics in period_metrics.items():
        period_end = _parse_period_label(label)
        if period_end is None:
            continue
        fiscal_year, fiscal_quarter = fiscal_label(period_end)
        quarters.append(
            BseQuarterlyResult(
                period_label=label,
                period_end_date=period_end,
                fiscal_year=fiscal_year,
                fiscal_quarter=fiscal_quarter,
                sales=metrics.get("sales"),
                pat=metrics.get("pat"),
                opm=metrics.get("opm"),
                npm=metrics.get("npm"),
            )
        )

    quarters.sort(key=lambda row: row.period_end_date)
    currency = str(payload.get("currency_unit") or payload.get("col1") or "").strip("() ")
    return BseResultsSnapshot(
        bse_code=bse_code,
        currency_unit=currency,
        quarters=tuple(quarters),
    )


def fetch_bse_results_snapshot(
    bse_code: str,
    *,
    timeout: float = 30.0,
    client: httpx.Client | None = None,
) -> BseResultsSnapshot:
    """Fetch and parse quarterly results for one BSE scrip code."""
    code = bse_code.strip()
    if not code:
        raise BseFinancialResultsFetchError("BSE code is required")

    last_error: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            if client is not None:
                payload = _fetch_payload(client, code, timeout=timeout)
            else:
                with httpx.Client(
                    headers=_bse_headers(),
                    timeout=timeout,
                    follow_redirects=True,
                ) as owned:
                    try:
                        owned.get("https://www.bseindia.com/")
                    except Exception:
                        pass
                    payload = _fetch_payload(owned, code, timeout=timeout)
            return parse_results_snapshot(code, payload)
        except Exception as exc:
            last_error = exc
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_BACKOFF_SEC * (attempt + 1))

    raise BseFinancialResultsFetchError(
        f"BSE financial results fetch failed for {code}: {last_error}"
    )


def _fetch_payload(client: httpx.Client, bse_code: str, *, timeout: float) -> dict[str, Any]:
    response = client.get(
        _RESULTS_URL,
        params={"scripcode": bse_code, "tabtype": "RESULTS"},
        timeout=timeout,
    )
    response.raise_for_status()
    payload: Any = response.json()
    if isinstance(payload, str):
        import json

        payload = json.loads(payload)
    if not isinstance(payload, dict):
        raise BseFinancialResultsFetchError("Unexpected BSE results payload type")
    return payload
