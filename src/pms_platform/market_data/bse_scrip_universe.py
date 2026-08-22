"""BSE equity scrip universe (ISIN / name → BSE code) for disclosure enrichment."""

from __future__ import annotations

import re
import time
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from pms_platform.market_data.bse_http import bse_headers as _bse_headers

_BSE_LIST_URL = "https://api.bseindia.com/BseIndiaAPI/api/ListOfScripData/w"
_CACHE_TTL_SEC = 24 * 60 * 60
_cache_loaded_at = 0.0
_isin_to_code: dict[str, str] = {}
_name_to_code: dict[str, str] = {}
_nse_to_code: dict[str, str] = {}
_code_to_meta: dict[str, dict[str, str]] = {}
_mktcap_by_code: dict[str, Decimal] = {}
_all_codes: set[str] = set()


def _norm_name(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "").casefold()).strip()
    text = re.sub(r"\beq\b", "", text).strip()
    text = re.sub(r"\blimited\b", "ltd", text)
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def refresh_bse_scrip_universe(*, force: bool = False) -> None:
    """Load Active Equity scrips from BSE into in-memory ISIN/name maps."""
    global _cache_loaded_at, _isin_to_code, _name_to_code, _nse_to_code, _code_to_meta, _mktcap_by_code, _all_codes
    now = time.time()
    if not force and _isin_to_code and now - _cache_loaded_at < _CACHE_TTL_SEC:
        return

    with httpx.Client(headers=_bse_headers(), timeout=120.0, follow_redirects=True) as client:
        try:
            client.get("https://www.bseindia.com/")
        except Exception:
            pass
        response = client.get(
            _BSE_LIST_URL,
            params={"segment": "Equity", "status": "Active"},
        )
        response.raise_for_status()
        payload = response.json()

    if not isinstance(payload, list):
        raise RuntimeError("Unexpected BSE ListOfScripData payload")

    isin_map: dict[str, str] = {}
    name_map: dict[str, str] = {}
    nse_map: dict[str, str] = {}
    code_meta: dict[str, dict[str, str]] = {}
    mktcap_map: dict[str, Decimal] = {}
    codes: set[str] = set()
    for row in payload:
        if not isinstance(row, dict):
            continue
        code = str(row.get("SCRIP_CD") or "").strip()
        if not code:
            continue
        codes.add(code)
        raw_cap = row.get("Mktcap")
        if raw_cap is not None:
            try:
                cap = Decimal(str(raw_cap).strip().replace(",", ""))
                if cap > 0:
                    mktcap_map[code] = cap
            except (InvalidOperation, ValueError):
                pass
        isin = str(row.get("ISIN_NUMBER") or "").strip().upper()
        scrip_name = str(row.get("Scrip_Name") or "").strip()
        nse_symbol = str(row.get("scrip_id") or "").strip().upper()
        code_meta[code] = {
            "bse_code": code,
            "isin": isin,
            "nse_symbol": nse_symbol,
            "scrip_name": scrip_name,
            "active": "Y",
        }
        if isin:
            isin_map[isin] = code
        name = _norm_name(scrip_name)
        if name and name not in name_map:
            name_map[name] = code
        if nse_symbol and nse_symbol not in nse_map:
            nse_map[nse_symbol] = code

    if not isin_map and not name_map:
        return

    _isin_to_code = isin_map
    _name_to_code = name_map
    _nse_to_code = nse_map
    _code_to_meta = code_meta
    _mktcap_by_code = mktcap_map
    _all_codes = codes
    _cache_loaded_at = now


def all_active_bse_codes() -> frozenset[str]:
    """Every active BSE equity scrip code."""
    refresh_bse_scrip_universe()
    return frozenset(_all_codes)


def resolve_bse_code(
    *,
    bse_code: object = None,
    isin: object = None,
    company_name: object = None,
    nse_symbol: object = None,
    allow_soft_name: bool = True,
) -> str | None:
    """Resolve a BSE scrip code from an explicit code, ISIN, NSE symbol, or company name."""
    direct = str(bse_code or "").strip()
    if direct.endswith(".0"):
        direct = direct[:-2]
    if direct and direct.lower() not in {"nan", "none", "null"}:
        return direct

    refresh_bse_scrip_universe()
    nse_key = str(nse_symbol or "").strip().upper()
    if nse_key and nse_key in _nse_to_code:
        return _nse_to_code[nse_key]

    isin_key = str(isin or "").strip().upper()
    if isin_key and isin_key in _isin_to_code:
        return _isin_to_code[isin_key]

    name_key = _norm_name(company_name)
    if name_key and name_key in _name_to_code:
        return _name_to_code[name_key]
    # Soft match: longest name that is contained in either direction.
    if allow_soft_name and name_key:
        best: tuple[int, str] | None = None
        for listed_name, code in _name_to_code.items():
            if name_key in listed_name or listed_name in name_key:
                score = min(len(name_key), len(listed_name))
                if best is None or score > best[0]:
                    best = (score, code)
        if best is not None and best[0] >= 8:
            return best[1]
    return None


def lookup_bse_scrip(bse_code: str) -> dict[str, str] | None:
    """Return ISIN/NSE/scrip name for an active BSE equity code."""
    code = str(bse_code or "").strip()
    if code.endswith(".0"):
        code = code[:-2]
    if not code:
        return None
    refresh_bse_scrip_universe()
    return _code_to_meta.get(code)


def ensure_scrip_universe_loaded() -> dict[str, Any]:
    refresh_bse_scrip_universe()
    return {
        "isin_count": len(_isin_to_code),
        "name_count": len(_name_to_code),
        "nse_count": len(_nse_to_code),
        "code_count": len(_code_to_meta),
        "loaded_at": _cache_loaded_at,
    }
