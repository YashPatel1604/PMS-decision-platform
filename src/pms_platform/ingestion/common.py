"""Shared ingestion helpers."""

import hashlib
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

LIQUID_PORTFOLIO_NAMES: frozenset[str] = frozenset({"LiquidCase", "Liquid Case", "LiquidBees"})


def is_liquid_holding(portfolio_name: str) -> bool:
    """Return True when the portfolio name represents liquid holdings."""
    return portfolio_name.strip() in LIQUID_PORTFOLIO_NAMES


def file_checksum(path: Path) -> str:
    """Return a SHA-256 checksum for a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_source_key(source_file: str, source_sheet: str, source_row: int) -> str:
    """Build a stable lineage key for an imported row."""
    return f"{source_file}|{source_sheet}|{source_row}"


def to_date(value: datetime | date) -> date:
    """Normalize workbook dates to plain dates."""
    if isinstance(value, datetime):
        return value.date()
    return value


def parse_workbook_date(value: object) -> date:
    """Parse an Excel cell value into a date."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    msg = f"Unsupported workbook date value: {value!r}"
    raise ValueError(msg)


def to_decimal(value: object | None) -> Decimal | None:
    """Convert numeric workbook values to Decimal."""
    if value is None or value == "":
        return None
    return Decimal(str(value))


def to_int_quantity(value: object) -> int:
    """Convert workbook quantity values to int."""
    if value is None or value == "":
        msg = "Quantity is required"
        raise ValueError(msg)
    if isinstance(value, bool):
        msg = "Quantity must be numeric"
        raise ValueError(msg)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return int(str(value))
