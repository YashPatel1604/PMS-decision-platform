"""Parse Research/Portfolio/PMS_ClientPortfolio.xlsx (Model + Stocks).

Read-only. Never writes back into Research.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import openpyxl

from pms_platform.research_paths import research_portfolio_dir

_SKIP = frozenset(
    {
        "model",
        "stock",
        "stocks",
        "symbol",
        "total",
        "total_value",
        "cash",
        "qnty",
        "portfolio",
        "balance_with_bank",
    }
)


@dataclass(frozen=True)
class ClientPortfolioPosition:
    symbol: str
    qty: Decimal
    excel_price: Decimal | None
    excel_value: Decimal | None
    excel_percent: Decimal | None
    index_label: str | None = None
    mcap: Decimal | None = None
    as_of_label: str | None = None  # Model!Date e.g. Nov25
    firm_pct: Decimal | None = None  # Model!%Firm
    target_value: Decimal | None = None  # second Value col (buy / target)
    portfolio_flag: str | None = None  # Model!Portfolio
    ramprasath_qty: Decimal | None = None  # Quantity!RAMPRASATH REDDY QTYN (static)


@dataclass(frozen=True)
class YearlyReturnRow:
    year: int
    start: Decimal | None
    end: Decimal | None
    return_pct: Decimal | None  # calendar-year return as percent points
    cum_pct: Decimal | None  # cumulative vs series start, percent points


@dataclass(frozen=True)
class YearlyReturnSeries:
    name: str
    rows: tuple[YearlyReturnRow, ...]


@dataclass(frozen=True)
class ClientPortfolioBook:
    path: Path
    mtime: float
    model: list[ClientPortfolioPosition]
    stocks_qty: dict[str, Decimal]
    excel_total_value: Decimal | None
    yearly: tuple[YearlyReturnSeries, ...] = field(default_factory=tuple)
    bank_balance: Decimal | None = None  # Quantity!F "Balance with Bank"


def client_portfolio_workbook_path() -> Path | None:
    portfolio = research_portfolio_dir()
    if portfolio is None:
        return None
    path = portfolio / "PMS_ClientPortfolio.xlsx"
    return path if path.is_file() else None


# ponytail: only literal a-b-c (WELENT Total Quantity), not cell refs
_NUMERIC_SUB = re.compile(r"^=\d+(?:\.\d+)?(?:-\d+(?:\.\d+)?)+$")


def _to_decimal(raw: object) -> Decimal | None:
    if raw is None or raw == "":
        return None
    text = str(raw).strip().replace(",", "").replace(" ", "")
    if _NUMERIC_SUB.fullmatch(text):
        parts = text[1:].split("-")
        total = Decimal(parts[0])
        for part in parts[1:]:
            total -= Decimal(part)
        return total
    try:
        return Decimal(text)
    except Exception:  # noqa: BLE001
        return None


def _symbol(raw: object) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip().upper()
    if not text or text.lower().replace(" ", "_") in _SKIP:
        return None
    return text


def _cell(row: tuple[Any, ...], idx: int) -> Any:
    return row[idx] if len(row) > idx else None


def _as_year(raw: object) -> int | None:
    if isinstance(raw, int) and 1990 <= raw <= 2100:
        return raw
    if isinstance(raw, float) and raw == int(raw) and 1990 <= int(raw) <= 2100:
        return int(raw)
    return None


def _pct_points(raw: object) -> Decimal | None:
    """Model yearly cells are Excel fractions / multiples (0.85 or 68.63×) → percent points."""
    value = _to_decimal(raw)
    if value is None:
        return None
    return value * Decimal(100)


def _parse_year_block(
    rows: list[tuple[Any, ...]], *, year_col: int
) -> list[YearlyReturnRow]:
    out: list[YearlyReturnRow] = []
    for row in rows:
        year = _as_year(_cell(row, year_col))
        if year is None:
            continue
        out.append(
            YearlyReturnRow(
                year=year,
                start=_to_decimal(_cell(row, year_col + 1)),
                end=_to_decimal(_cell(row, year_col + 2)),
                return_pct=_pct_points(_cell(row, year_col + 3)),
                cum_pct=_pct_points(_cell(row, year_col + 4)),
            )
        )
    return out


def _label_at(row: tuple[Any, ...], idx: int) -> str | None:
    raw = _cell(row, idx)
    if raw is None or raw == "":
        return None
    if _as_year(raw) is not None:
        return None
    text = str(raw).strip()
    if not text or text in {"-", " "}:
        return None
    return text


def _is_midcap_header(row: tuple[Any, ...]) -> bool:
    label = _label_at(row, 10)
    if not label:
        return False
    return label.upper().replace(" ", "") in {"BSEMIDCAP", "MIDCAP"}


def _parse_yearly_series(rows: list[tuple[Any, ...]]) -> list[YearlyReturnSeries]:
    """Pull Portfolio / benchmark year blocks from the Model sheet layout."""
    series: list[YearlyReturnSeries] = []

    def add(name: str, year_col: int, block: list[tuple[Any, ...]]) -> None:
        parsed = _parse_year_block(block, year_col=year_col)
        if parsed:
            series.append(YearlyReturnSeries(name=name, rows=tuple(parsed)))

    mid_idx = next((i for i, row in enumerate(rows) if _is_midcap_header(row)), None)
    bse500_idx = next(
        (
            i
            for i, row in enumerate(rows)
            if str(_cell(row, 10) or "").strip().upper() == "BSE500"
        ),
        None,
    )
    top = rows if mid_idx is None else rows[:mid_idx]
    if mid_idx is None:
        bottom: list[tuple[Any, ...]] = []
    elif bse500_idx is not None and bse500_idx > mid_idx:
        bottom = rows[mid_idx:bse500_idx]
    else:
        bottom = rows[mid_idx:]

    # Header: Portfolio years @ col 11, BSESmallCap @ col 16/17
    add("Portfolio", 11, top)
    small_name = _label_at(rows[0], 16) if rows else None
    add(small_name or "BSESmallCap", 17, top)

    if bottom:
        mid_name = _label_at(bottom[0], 10) or "BSEMidCap"
        add(mid_name, 11, bottom)
        sensex = _label_at(bottom[0], 16)
        add(sensex or "Sensex", 17, bottom)

    # BSE500 sits under the Portfolio/MidCap columns (label @ col 10, year @ 11).
    if bse500_idx is not None:
        add("BSE500", 11, rows[bse500_idx:])

    return series


def parse_client_portfolio_workbook(path: Path) -> ClientPortfolioBook:
    """Load Model holdings + Stocks quantities from the live client workbook."""
    mtime = path.stat().st_mtime
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        model_rows = (
            [tuple(r) for r in workbook["Model"].iter_rows(values_only=True)]
            if "Model" in workbook.sheetnames
            else []
        )
        stocks_rows = (
            [tuple(r) for r in workbook["Stocks"].iter_rows(values_only=True)]
            if "Stocks" in workbook.sheetnames
            else []
        )
        has_quantity = "Quantity" in workbook.sheetnames
    finally:
        workbook.close()

    # Quantity Total Quantity may be literal a-b-c formulas (WELENT); need formula cells.
    quantity_rows: list[tuple[Any, ...]] = []
    if has_quantity:
        qty_wb = openpyxl.load_workbook(path, read_only=True, data_only=False)
        try:
            quantity_rows = [
                tuple(r) for r in qty_wb["Quantity"].iter_rows(values_only=True)
            ]
        finally:
            qty_wb.close()

    yearly = tuple(_parse_yearly_series(model_rows))

    model: list[ClientPortfolioPosition] = []
    excel_total: Decimal | None = None
    for row in model_rows:
        if not row or row[0] is None:
            continue
        label = str(row[0]).strip()
        lower = label.lower().replace(" ", "_")
        if lower in {"total_value", "total"}:
            excel_total = _to_decimal(row[3] if len(row) > 3 else None)
            continue
        symbol = _symbol(row[0])
        if symbol is None:
            continue
        qty = _to_decimal(row[1] if len(row) > 1 else None)
        if qty is None or qty == 0:
            continue
        portfolio_raw = _label_at(row, 10)
        # Col 10 is also where MidCap series title sits — only keep stock flags.
        portfolio_flag = None
        if portfolio_raw and portfolio_raw.upper().replace(" ", "") not in {
            "BSEMIDCAP",
            "MIDCAP",
            "BSESMALLCAP",
            "SENSEX",
            "BSE500",
            "PORTFOLIO",
        }:
            portfolio_flag = portfolio_raw
        model.append(
            ClientPortfolioPosition(
                symbol=symbol,
                qty=qty,
                excel_price=_to_decimal(_cell(row, 2)),
                excel_value=_to_decimal(_cell(row, 3)),
                excel_percent=_to_decimal(_cell(row, 4)),
                index_label=(
                    str(_cell(row, 5)).strip()
                    if _cell(row, 5) not in (None, "")
                    else None
                ),
                mcap=_to_decimal(_cell(row, 6)),
                as_of_label=(
                    str(_cell(row, 7)).strip()
                    if _cell(row, 7) not in (None, "")
                    else None
                ),
                firm_pct=_to_decimal(_cell(row, 8)),
                target_value=_to_decimal(_cell(row, 9)),
                portfolio_flag=portfolio_flag,
            )
        )

    # Fallback: some broker books provide only Quantity sheet (no Model layout).
    if not model and quantity_rows:
        for row in quantity_rows:
            if not row or row[0] is None:
                continue
            symbol = _symbol(row[0])
            if symbol is None:
                continue
            qty = _to_decimal(_cell(row, 3))
            if qty is None or qty == 0:
                continue
            ramprasath = _to_decimal(_cell(row, 7))
            model.append(
                ClientPortfolioPosition(
                    symbol=symbol,
                    qty=qty,
                    excel_price=_to_decimal(_cell(row, 4)),
                    excel_value=_to_decimal(_cell(row, 5)),
                    excel_percent=_to_decimal(_cell(row, 2)),
                    ramprasath_qty=ramprasath,
                )
            )

    stocks_qty: dict[str, Decimal] = {}
    for row in stocks_rows:
        if not row or row[0] is None:
            continue
        symbol = _symbol(row[0])
        if symbol is None:
            continue
        # Stocks: SYMBOL, name, price, blank, Quantity, Value
        qty = _to_decimal(row[4] if len(row) > 4 else None)
        if qty is None:
            continue
        stocks_qty[symbol] = qty

    if not stocks_qty and quantity_rows:
        for row in quantity_rows:
            if not row or row[0] is None:
                continue
            symbol = _symbol(row[0])
            if symbol is None:
                continue
            qty = _to_decimal(_cell(row, 3))
            if qty is None:
                continue
            stocks_qty[symbol] = qty

    bank_balance: Decimal | None = None
    for row in quantity_rows:
        if not row or row[0] is None:
            continue
        if str(row[0]).strip().lower().replace(" ", "_") == "balance_with_bank":
            bank_balance = _to_decimal(_cell(row, 5))
            break

    return ClientPortfolioBook(
        path=path,
        mtime=mtime,
        model=model,
        stocks_qty=stocks_qty,
        excel_total_value=excel_total,
        yearly=yearly,
        bank_balance=bank_balance,
    )


@lru_cache(maxsize=4)
def _cached_book(path_str: str, mtime: float) -> ClientPortfolioBook:
    return parse_client_portfolio_workbook(Path(path_str))


def load_client_portfolio_book(path: Path | None = None) -> ClientPortfolioBook | None:
    """Load (and cache) the live client portfolio workbook."""
    resolved = path or client_portfolio_workbook_path()
    if resolved is None or not resolved.is_file():
        return None
    mtime = resolved.stat().st_mtime
    return _cached_book(str(resolved.resolve()), mtime)


def clear_client_portfolio_cache() -> None:
    _cached_book.cache_clear()


def book_meta(book: ClientPortfolioBook) -> dict[str, Any]:
    return {
        "source_file": str(book.path),
        "excel_mtime": datetime.fromtimestamp(book.mtime).isoformat(timespec="seconds"),
        "excel_total_value": float(book.excel_total_value)
        if book.excel_total_value is not None
        else None,
        "bank_balance": float(book.bank_balance) if book.bank_balance is not None else None,
        "model_count": len(book.model),
    }


def yearly_as_dicts(book: ClientPortfolioBook) -> list[dict[str, Any]]:
    return [
        {
            "name": series.name,
            "rows": [
                {
                    "year": row.year,
                    "start": float(row.start) if row.start is not None else None,
                    "end": float(row.end) if row.end is not None else None,
                    "return_pct": float(row.return_pct)
                    if row.return_pct is not None
                    else None,
                    "cum_pct": float(row.cum_pct) if row.cum_pct is not None else None,
                }
                for row in series.rows
            ],
        }
        for series in book.yearly
    ]
