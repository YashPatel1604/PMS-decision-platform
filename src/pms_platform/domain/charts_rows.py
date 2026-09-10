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


def parsed_rows_from_db(session: Session) -> list[dict[str, Any]]:
    """Charts dashboard rows from DB when DailyEdit Charts.xlsx is absent."""
    rows = session.scalars(select(ChartsRangeRow).order_by(ChartsRangeRow.excel_row)).all()
    return [
        {
            "name": row.name,
            "symbol": row.symbol,
            "section": row.section,
            "excel_row": row.excel_row,
            "series": "EQ",
            "high": row.high,
            "low": row.low,
            "excel_close": row.close_override,
            "weekly_close": row.weekly_close,
            "support_resistance": row.support_resistance,
            "weekly_close_date": row.weekly_close_date,
        }
        for row in rows
    ]


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


def reimport_rows_from_parse(
    session: Session,
    parsed: list[dict[str, Any]],
    *,
    dry_run: bool = False,
    replace_levels: bool = False,
) -> dict[str, Any]:
    """Sync Charts Range from Excel. With replace_levels, overwrite H/L/C/weekly too."""
    excel_rows = {int(raw["excel_row"]): raw for raw in parsed}
    official = {r.excel_row: r for r in session.scalars(select(ChartsRangeRow)).all()}
    added = sorted(set(excel_rows) - set(official))
    removed = sorted(set(official) - set(excel_rows))
    updated: list[int] = []
    for excel_row, raw in excel_rows.items():
        row = official.get(excel_row)
        if row is None:
            continue
        struct_changed = (
            row.symbol != str(raw["symbol"])
            or row.name != str(raw["name"])
            or row.section != str(raw.get("section") or "holdings")
        )
        levels_changed = False
        if replace_levels:
            new_high = raw.get("high")
            new_low = raw.get("low")
            new_close = raw.get("excel_close")
            levels_changed = (
                (row.high is None) != (new_high is None)
                or (row.high is not None and new_high is not None and row.high != Decimal(str(new_high)))
                or (row.low is None) != (new_low is None)
                or (row.low is not None and new_low is not None and row.low != Decimal(str(new_low)))
                or (row.close_override is None) != (new_close is None)
                or (
                    row.close_override is not None
                    and new_close is not None
                    and row.close_override != Decimal(str(new_close))
                )
            )
        if struct_changed or levels_changed:
            updated.append(excel_row)

    if dry_run:
        return {"added": added, "removed": removed, "updated": updated}

    for excel_row in removed:
        session.delete(official[excel_row])
    for excel_row in added:
        raw = excel_rows[excel_row]
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
    session.flush()
    official = {r.excel_row: r for r in session.scalars(select(ChartsRangeRow)).all()}
    for excel_row, raw in excel_rows.items():
        row = official.get(excel_row)
        if row is None:
            continue
        row.symbol = str(raw["symbol"])
        row.name = str(raw["name"])
        row.section = str(raw.get("section") or "holdings")
        if replace_levels:
            row.high = Decimal(str(raw["high"])) if raw.get("high") is not None else None
            row.low = Decimal(str(raw["low"])) if raw.get("low") is not None else None
            row.close_override = (
                Decimal(str(raw["excel_close"])) if raw.get("excel_close") is not None else None
            )
            row.weekly_close = (
                Decimal(str(raw["weekly_close"])) if raw.get("weekly_close") is not None else None
            )
            row.support_resistance = raw.get("support_resistance")
            row.weekly_close_date = raw.get("weekly_close_date")
        row.row_version = row.row_version + 1
    session.flush()
    return {"added": added, "removed": removed, "updated": updated}


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
