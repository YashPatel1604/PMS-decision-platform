"""Shared market-data parsing helpers."""

from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from pms_platform.ingestion.common import file_checksum, make_source_key


def make_csv_source_key(source_file: str, source_row: int) -> str:
    """Build a stable lineage key for a canonical CSV row."""
    return make_source_key(source_file, "csv", source_row)


def parse_iso_date(value: object, field_name: str) -> date | None:
    """Parse an optional ISO date from a CSV cell."""
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip()
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        msg = f"Invalid {field_name}: {value!r}"
        raise ValueError(msg) from exc


def parse_required_iso_date(value: object, field_name: str) -> date:
    """Parse a required ISO date from a CSV cell."""
    parsed = parse_iso_date(value, field_name)
    if parsed is None:
        msg = f"Missing required {field_name}"
        raise ValueError(msg)
    return parsed


def parse_decimal(value: object, field_name: str) -> Decimal:
    """Parse a required decimal from a CSV cell."""
    if value is None or str(value).strip() == "":
        msg = f"Missing required {field_name}"
        raise ValueError(msg)
    try:
        return Decimal(str(value).strip())
    except InvalidOperation as exc:
        msg = f"Invalid {field_name}: {value!r}"
        raise ValueError(msg) from exc


def parse_optional_int(value: object) -> int | None:
    """Parse an optional integer from a CSV cell."""
    if value is None or str(value).strip() == "":
        return None
    return int(float(str(value).strip()))


def read_csv_rows(path: Path) -> tuple[list[dict[str, str]], list[str] | None]:
    """Read a CSV file into row dictionaries and return field names."""
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            msg = f"CSV file has no header row: {path}"
            raise ValueError(msg)
        return [dict(row) for row in reader], list(reader.fieldnames)


def validate_required_columns(path: Path, required_columns: tuple[str, ...]) -> None:
    """Ensure a CSV contains the expected header columns."""
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            msg = f"CSV file has no header row: {path}"
            raise ValueError(msg)
        missing = [column for column in required_columns if column not in reader.fieldnames]
        if missing:
            msg = f"{path} is missing required columns: {', '.join(missing)}"
            raise ValueError(msg)


def directory_checksum(paths: list[Path]) -> str:
    """Return a combined checksum for a set of files."""
    import hashlib

    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.name.encode())
        digest.update(file_checksum(path).encode())
    return digest.hexdigest()
