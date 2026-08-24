"""BSE shareholding pattern fetcher — promoter holding and pledged percentage."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from pms_platform.market_data.bse_http import bse_headers

_DECLARATION_URL = "https://api.bseindia.com/BseIndiaAPI/api/shpDecleraction/w"
_SUMMARY_URL = "https://api.bseindia.com/BseIndiaAPI/api/CorporatesSHPSecuritybeta/w"
_MAX_RETRIES = 3
_RETRY_DELAY_SEC = 0.8


class BseShareholdingFetchError(Exception):
    """Raised when the shareholding API returns an unusable response."""


@dataclass(frozen=True)
class BseShareholdingSnapshot:
    """Latest promoter shareholding data for one scrip."""

    bse_code: str
    quarter_end_date: date
    quarter_name: str | None
    promoter_holding_pct: Decimal | None
    pledged_pct: Decimal | None


def _to_dec(raw: object) -> Decimal | None:
    if raw is None:
        return None
    text = str(raw).strip().replace(",", "").replace("%", "")
    if not text or text.lower() in {"nan", "none", "null", "-", "—", "--", "na", "n/a"}:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _parse_quarter_end(raw: object) -> date | None:
    text = str(raw or "").strip()
    if not text:
        return None
    for fmt in ("%d %b %Y", "%d/%m/%Y", "%Y-%m-%d", "%b-%y", "%B %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _qtr_id(raw: object) -> str | None:
    if raw is None:
        return None
    try:
        return str(int(float(str(raw).strip())))
    except (TypeError, ValueError):
        text = str(raw).strip()
        return text or None


def _latest_declaration(client: httpx.Client, bse_code: str, *, timeout: float) -> dict[str, Any] | None:
    for attempt in range(_MAX_RETRIES):
        try:
            resp = client.get(
                _DECLARATION_URL,
                params={"scripcode": bse_code, "qtrid": ""},
                timeout=timeout,
            )
            if resp.status_code != 200 or len(resp.content) < 10:
                time.sleep(_RETRY_DELAY_SEC * (attempt + 1))
                continue
            payload = resp.json()
            if isinstance(payload, list) and payload and isinstance(payload[0], dict):
                return payload[0]
            if isinstance(payload, dict) and isinstance(payload.get("Table"), list) and payload["Table"]:
                row = payload["Table"][0]
                if isinstance(row, dict):
                    return row
        except Exception:
            time.sleep(_RETRY_DELAY_SEC * (attempt + 1))
    return None


def _summary_payload(
    client: httpx.Client,
    bse_code: str,
    qtr_id: str,
    *,
    timeout: float,
) -> dict[str, Any] | None:
    for attempt in range(_MAX_RETRIES):
        try:
            resp = client.get(
                _SUMMARY_URL,
                params={"scripcode": bse_code, "qtrid": qtr_id},
                timeout=timeout,
            )
            if resp.status_code != 200 or len(resp.content) < 20:
                time.sleep(_RETRY_DELAY_SEC * (attempt + 1))
                continue
            payload = resp.json()
            if isinstance(payload, dict):
                return payload
        except Exception:
            time.sleep(_RETRY_DELAY_SEC * (attempt + 1))
    return None


def _promoter_from_summary(payload: dict[str, Any]) -> tuple[Decimal | None, Decimal | None]:
    rows = payload.get("Table1") or payload.get("Table5") or []
    if not isinstance(rows, list):
        return None, None
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("Fld_ShortName") or row.get("Fld_ShortCatg") or "").lower()
        if "promoter" not in name:
            continue
        holding = _to_dec(
            row.get("Fld_TotalPercentageOf_A_B_C2")
            or row.get("Fld_TotalVotingRightsPercent")
        )
        pledged = _to_dec(
            row.get("Fld_PledgeEncumberedPercentage")
            or row.get("Fld_TotalencumberedPercentage")
        )
        return holding, pledged
    return None, None


def fetch_bse_shareholding(
    bse_code: str,
    *,
    timeout: float = 15.0,
    client: httpx.Client | None = None,
) -> BseShareholdingSnapshot | None:
    """Fetch latest promoter shareholding for one BSE scrip."""

    def _do_fetch(c: httpx.Client) -> BseShareholdingSnapshot | None:
        try:
            c.get("https://www.bseindia.com/")
        except Exception:
            pass
        declaration = _latest_declaration(c, bse_code, timeout=timeout)
        if declaration is None:
            return None
        qtr = _qtr_id(declaration.get("qtr_id"))
        if not qtr:
            return None
        summary = _summary_payload(c, bse_code, qtr, timeout=timeout)
        if summary is None:
            return None

        holding, pledged = _promoter_from_summary(summary)
        meta_rows = summary.get("Table3") if isinstance(summary.get("Table3"), list) else []
        meta = meta_rows[0] if meta_rows and isinstance(meta_rows[0], dict) else {}
        quarter_name = str(
            meta.get("fld_quartername")
            or declaration.get("qtr_name")
            or ""
        ).strip() or None
        quarter_end = (
            _parse_quarter_end(meta.get("fld_enddate"))
            or _parse_quarter_end(quarter_name)
            or date.today()
        )
        if holding is None and pledged is None:
            return None
        return BseShareholdingSnapshot(
            bse_code=bse_code,
            quarter_end_date=quarter_end,
            quarter_name=quarter_name,
            promoter_holding_pct=holding,
            pledged_pct=pledged,
        )

    if client is not None:
        return _do_fetch(client)
    with httpx.Client(headers=bse_headers(), follow_redirects=True) as c:
        return _do_fetch(c)


def fetch_bse_shareholding_batch(
    bse_codes: list[str],
    *,
    timeout: float = 15.0,
    delay_sec: float = 0.35,
) -> dict[str, BseShareholdingSnapshot | None]:
    """Fetch shareholding snapshots for multiple BSE scrips."""
    results: dict[str, BseShareholdingSnapshot | None] = {}
    with httpx.Client(headers=bse_headers(), follow_redirects=True) as client:
        for i, code in enumerate(bse_codes):
            if i > 0:
                time.sleep(delay_sec)
            results[code] = fetch_bse_shareholding(code, timeout=timeout, client=client)
    return results
