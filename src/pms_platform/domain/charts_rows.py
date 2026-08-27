"""Charts Range rows: DB store and direct writes (no approval — not holdings data)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.models.charts_range import ChartsRangeRow


def sync_rows_from_parse(session: Session, parsed: list[dict[str, Any]]) -> None:
    """Seed missing rows from Excel parse (idempotent)."""
    existing = {r.excel_row: r for r in session.scalars(select(ChartsRangeRow)).all()}
    for raw in parsed:
        excel_row = int(raw["excel_row"])
        if excel_row in existing:
            continue
        session.add(
            ChartsRangeRow(
                excel_row=excel_row,
                symbol=str(raw["symbol"]),
                name=str(raw["name"]),
                section=str(raw.get("section") or "holdings"),
                high=raw.get("high"),
                low=raw.get("low"),
                close_override=raw.get("excel_close"),
                weekly_close=raw.get("weekly_close"),
                support_resistance=raw.get("support_resistance"),
                weekly_close_date=raw.get("weekly_close_date"),
                row_version=1,
            )
        )


def ensure_charts_row(session: Session, excel_row: int) -> ChartsRangeRow:
    """Return DB row, seeding from Excel on first touch."""
    row = session.get(ChartsRangeRow, excel_row)
    if row is not None:
        return row
    from pms_platform.market_data.charts_dashboard import charts_workbook_path, parse_charts_range

    path = charts_workbook_path()
    if path is None or not path.is_file():
        raise ValueError("Charts workbook not found")
    sync_rows_from_parse(session, parse_charts_range(path))
    session.flush()
    row = session.get(ChartsRangeRow, excel_row)
    if row is None:
        raise ValueError("charts row not found")
    return row


def merge_db_into_parsed(session: Session, parsed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    official = {r.excel_row: r for r in session.scalars(select(ChartsRangeRow)).all()}
    out: list[dict[str, Any]] = []
    for raw in parsed:
        copy = dict(raw)
        row = official.get(int(raw["excel_row"]))
        if row is not None:
            if row.high is not None:
                copy["high"] = row.high
            if row.low is not None:
                copy["low"] = row.low
            if row.close_override is not None:
                copy["excel_close"] = row.close_override
            if row.weekly_close is not None:
                copy["weekly_close"] = row.weekly_close
            if row.support_resistance is not None:
                copy["support_resistance"] = row.support_resistance
            if row.weekly_close_date is not None:
                copy["weekly_close_date"] = row.weekly_close_date
        out.append(copy)
    return out


def apply_row_patch(
    session: Session,
    *,
    excel_row: int,
    patch: dict[str, Any],
    updated_by: int | None = None,
) -> ChartsRangeRow:
    row = ensure_charts_row(session, excel_row)
    if "high" in patch:
        row.high = Decimal(str(patch["high"])) if patch["high"] is not None else None
    if "low" in patch:
        row.low = Decimal(str(patch["low"])) if patch["low"] is not None else None
    if "close" in patch:
        row.close_override = Decimal(str(patch["close"])) if patch["close"] is not None else None
    if "weekly_close" in patch:
        row.weekly_close = (
            Decimal(str(patch["weekly_close"])) if patch["weekly_close"] is not None else None
        )
    if "support_resistance" in patch:
        row.support_resistance = patch["support_resistance"]
    if "weekly_close_date" in patch:
        row.weekly_close_date = patch["weekly_close_date"]
    row.row_version = row.row_version + 1
    if updated_by is not None:
        row.updated_by = updated_by
    session.flush()
    return row
