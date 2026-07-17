"""Normalize external package CSV rows into canonical market-data fields."""

from __future__ import annotations

from pathlib import Path

from pms_platform.market_data.contracts import (
    BENCHMARK_TRI_COLUMNS,
    DAILY_PRICES_COLUMNS,
    DIVIDENDS_COLUMNS,
    SECURITY_SUCCESSORS_COLUMNS,
)

EXTERNAL_PRICE_COLUMNS: frozenset[str] = frozenset(
    {
        "security_id",
        "symbol",
        "trade_date",
        "close",
        "adjusted_close",
        "adjustment_scope",
        "volume",
        "currency",
        "source",
        "retrieved_at",
    }
)

EXTERNAL_SUCCESSOR_COLUMNS: frozenset[str] = frozenset(
    {
        "predecessor_security_id",
        "successor_security_id",
        "effective_date",
        "event_type",
        "verification_status",
    }
)

EXTERNAL_BENCHMARK_COLUMNS: frozenset[str] = frozenset(
    {
        "benchmark_id",
        "benchmark_name",
        "trade_date",
        "tri_level",
        "source",
        "retrieved_at",
    }
)

EXTERNAL_DIVIDEND_COLUMNS: frozenset[str] = frozenset(
    {
        "security_id",
        "symbol",
        "ex_date",
        "dividend_per_share",
        "currency",
        "source",
        "retrieved_at",
    }
)

_ADJUSTMENT_SCOPE_MAP = {
    "SPLIT_BONUS": "SPLIT_AND_DIVIDEND",
    "SPLIT_ONLY": "SPLIT_ONLY",
    "SPLIT_AND_DIVIDEND": "SPLIT_AND_DIVIDEND",
    "TOTAL_RETURN": "TOTAL_RETURN",
    "VENDOR_ADJUSTED": "VENDOR_ADJUSTED",
}

_EVENT_TYPE_MAP = {
    "NAME_SYMBOL_CHANGE": "RENAME",
    "DEMERGER": "DEMERGER",
    "DEMERGER_MERGER": "MERGER",
    "MERGER": "MERGER",
    "DELISTING": "DELISTING",
    "CONVERSION": "CONVERSION",
}


def _has_columns(fieldnames: list[str] | None, required: frozenset[str]) -> bool:
    if fieldnames is None:
        return False
    return required.issubset(set(fieldnames))


def is_canonical_price_format(fieldnames: list[str] | None) -> bool:
    return _has_columns(fieldnames, frozenset(DAILY_PRICES_COLUMNS))


def is_external_price_format(fieldnames: list[str] | None) -> bool:
    return _has_columns(fieldnames, EXTERNAL_PRICE_COLUMNS)


def is_canonical_successor_format(fieldnames: list[str] | None) -> bool:
    return _has_columns(fieldnames, frozenset(SECURITY_SUCCESSORS_COLUMNS))


def is_external_successor_format(fieldnames: list[str] | None) -> bool:
    return _has_columns(fieldnames, EXTERNAL_SUCCESSOR_COLUMNS)


def is_canonical_dividend_format(fieldnames: list[str] | None) -> bool:
    return _has_columns(fieldnames, frozenset(DIVIDENDS_COLUMNS))


def is_external_dividend_format(fieldnames: list[str] | None) -> bool:
    return _has_columns(fieldnames, EXTERNAL_DIVIDEND_COLUMNS)


def is_canonical_benchmark_format(fieldnames: list[str] | None) -> bool:
    return _has_columns(fieldnames, frozenset(BENCHMARK_TRI_COLUMNS))


def is_external_benchmark_format(fieldnames: list[str] | None) -> bool:
    return _has_columns(fieldnames, EXTERNAL_BENCHMARK_COLUMNS)


def validate_price_columns(path: Path, fieldnames: list[str] | None) -> None:
    if is_canonical_price_format(fieldnames) or is_external_price_format(fieldnames):
        return
    msg = (
        f"{path} must contain canonical price columns or external package columns "
        f"(security_id, symbol, trade_date, close, adjusted_close, ...)"
    )
    raise ValueError(msg)


def validate_successor_columns(path: Path, fieldnames: list[str] | None) -> None:
    if is_canonical_successor_format(fieldnames) or is_external_successor_format(fieldnames):
        return
    msg = f"{path} must contain canonical or external successor columns"
    raise ValueError(msg)


def validate_benchmark_columns(path: Path, fieldnames: list[str] | None) -> None:
    if fieldnames is None:
        msg = f"CSV file has no header row: {path}"
        raise ValueError(msg)
    if _has_columns(fieldnames, frozenset(BENCHMARK_TRI_COLUMNS)):
        return
    if _has_columns(fieldnames, EXTERNAL_BENCHMARK_COLUMNS):
        return
    msg = f"{path} must contain canonical or external benchmark columns"
    raise ValueError(msg)


def validate_dividend_columns(path: Path, fieldnames: list[str] | None) -> None:
    if fieldnames is None:
        msg = f"CSV file has no header row: {path}"
        raise ValueError(msg)
    if _has_columns(fieldnames, frozenset(DIVIDENDS_COLUMNS)):
        return
    if _has_columns(fieldnames, EXTERNAL_DIVIDEND_COLUMNS):
        return
    msg = f"{path} must contain canonical or external dividend columns"
    raise ValueError(msg)


def _publication_date(value: str | None) -> str:
    if not value:
        return ""
    text = value.strip()
    if "T" in text:
        return text.split("T", maxsplit=1)[0]
    return text[:10]


def normalize_price_row(row: dict[str, str], *, canonical: bool) -> dict[str, str]:
    if canonical:
        return row
    scope = (row.get("adjustment_scope") or "SPLIT_BONUS").strip().upper()
    adjustment_basis = _ADJUSTMENT_SCOPE_MAP.get(scope, "VENDOR_ADJUSTED")
    identifier_type = "SECURITY_ID" if row.get("security_id") else "NSE_SYMBOL"
    identifier = row.get("security_id") or row.get("symbol") or ""
    return {
        "identifier_type": identifier_type,
        "identifier": identifier.strip(),
        "trade_date": row["trade_date"].strip(),
        "close": row["close"].strip(),
        "adjusted_close": row["adjusted_close"].strip(),
        "adjustment_basis": adjustment_basis,
        "volume": (row.get("volume") or "").strip(),
        "currency": (row.get("currency") or "INR").strip(),
        "source": row["source"].strip(),
        "publication_date": _publication_date(row.get("retrieved_at")),
    }


def normalize_dividend_row(row: dict[str, str], *, canonical: bool) -> dict[str, str]:
    if canonical:
        return row
    identifier_type = "SECURITY_ID" if row.get("security_id") else "NSE_SYMBOL"
    identifier = row.get("security_id") or row.get("symbol") or ""
    return {
        "identifier_type": identifier_type,
        "identifier": identifier.strip(),
        "ex_date": row["ex_date"].strip(),
        "record_date": (row.get("record_date") or "").strip(),
        "payment_date": (row.get("payment_date") or "").strip(),
        "dividend_per_share": row["dividend_per_share"].strip(),
        "currency": (row.get("currency") or "INR").strip(),
        "source": row["source"].strip(),
        "publication_date": _publication_date(row.get("retrieved_at")),
    }


def normalize_benchmark_row(row: dict[str, str], *, canonical: bool) -> dict[str, str]:
    if canonical:
        return row
    benchmark_code = (row.get("benchmark_id") or row.get("benchmark_name") or "").strip().upper()
    return {
        "benchmark_code": benchmark_code,
        "trade_date": row["trade_date"].strip(),
        "tri_level": row["tri_level"].strip(),
        "source": row["source"].strip(),
        "publication_date": _publication_date(row.get("retrieved_at")),
        "methodology_version": (row.get("methodology_version") or "").strip(),
    }


def normalize_successor_row(row: dict[str, str], *, canonical: bool) -> dict[str, str] | None:
    if canonical:
        return row

    effective_date = (row.get("effective_date") or "").strip()
    if not effective_date:
        return None

    event_type = (row.get("event_type") or row.get("action_type") or "").strip().upper()
    action_type = _EVENT_TYPE_MAP.get(event_type, event_type)
    verification = (row.get("verification_status") or row.get("confirmed") or "").strip().upper()
    confirmed = verification.startswith("CONFIRMED") or verification in {"TRUE", "YES", "1"}

    predecessor = row["predecessor_security_id"].strip()
    successor = row["successor_security_id"].strip()
    if not predecessor.startswith("SEC") or not successor.startswith("SEC"):
        return None

    return {
        "predecessor_security_id": predecessor,
        "successor_security_id": successor,
        "effective_date": effective_date,
        "action_type": action_type,
        "confirmed": "true" if confirmed else "false",
    }
