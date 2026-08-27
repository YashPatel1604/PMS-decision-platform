"""Parse PMS_ClientPortfolio.xlsx (Model + Stocks).

DailyEditFiles first, then Research/Portfolio. Never writes Research.
"""

from __future__ import annotations

import os
import re
import tempfile
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
    from pms_platform.market_data.daily_edit_bhav import client_portfolio_daily_edit_path

    hit = client_portfolio_daily_edit_path()
    if hit is not None:
        return hit
    portfolio = research_portfolio_dir()
    if portfolio is None:
        return None
    path = portfolio / "PMS_ClientPortfolio.xlsx"
    return path if path.is_file() else None


def client_portfolio_write_path() -> Path:
    """Writable DailyEditFiles workbook only (Research is read-only in Docker)."""
    from pms_platform.market_data.daily_edit_bhav import client_portfolio_daily_edit_path

    hit = client_portfolio_daily_edit_path()
    if hit is not None and hit.is_file():
        return hit
    raise FileNotFoundError(
        "PMS_ClientPortfolio*.xlsx not found in DailyEditFiles. "
        "Copy the workbook there (Research is read-only in Docker)."
    )

# ponytail: only literal a-b-c (WELENT Total Quantity), not cell refs
_NUMERIC_SUB = re.compile(r"^=\d+(?:\.\d+)?(?:-\d+(?:\.\d+)?)+$")
# Model!Mcap like =(19.11/2)*C3 or =(20.6/1)*C9 — openpyxl save clears cached values.
_MCAP_FORMULA = re.compile(
    r"^=\(?(\d+(?:\.\d+)?)(?:/(\d+(?:\.\d+)?))?\)?\*[A-Z]+\d+$",
    re.IGNORECASE,
)


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
    raw: list[tuple[int, Decimal | None, Decimal | None, Decimal | None, Decimal | None]] = []
    for row in rows:
        year = _as_year(_cell(row, year_col))
        if year is None:
            continue
        start = _to_decimal(_cell(row, year_col + 1))
        end = _to_decimal(_cell(row, year_col + 2))
        ret = _pct_points(_cell(row, year_col + 3))
        cum = _pct_points(_cell(row, year_col + 4))
        # openpyxl save clears Excel formula caches → Return/Cum often None; recompute.
        if ret is None and start is not None and end is not None and start != 0:
            ret = (end / start - 1) * Decimal(100)
        raw.append((year, start, end, ret, cum))

    first_start = next((s for _, s, _, _, _ in raw if s is not None), None)
    out: list[YearlyReturnRow] = []
    for year, start, end, ret, cum in raw:
        if cum is None and first_start is not None and first_start != 0 and end is not None:
            cum = (end / first_start - 1) * Decimal(100)
        out.append(
            YearlyReturnRow(year=year, start=start, end=end, return_pct=ret, cum_pct=cum)
        )
    return out


def _mcap_from_formula(formula: object, price: Decimal | None) -> Decimal | None:
    """Evaluate Model!Mcap share-factor × price when Excel cache is empty."""
    if price is None or not isinstance(formula, str) or not formula.startswith("="):
        return None
    match = _MCAP_FORMULA.fullmatch(formula.replace(" ", ""))
    if match is None:
        return None
    num = Decimal(match.group(1))
    den = Decimal(match.group(2) or "1")
    if den == 0:
        return None
    return (num / den) * price


def _firm_pct_from_parts(
    stocks_qty: Decimal | None, price: Decimal | None, mcap: Decimal | None
) -> Decimal | None:
    """Model!%Firm = (Stocks qty × price) / (Mcap × 1e5)."""
    if stocks_qty is None or price is None or mcap is None or mcap == 0:
        return None
    return (stocks_qty * price) / (mcap * Decimal(100_000))


def _fill_missing_mcap_firm(
    model: list[ClientPortfolioPosition],
    *,
    path: Path,
    stocks_qty: dict[str, Decimal],
    stocks_price: dict[str, Decimal],
) -> list[ClientPortfolioPosition]:
    """Recompute Mcap / %Firm when data_only cache was wiped (e.g. after openpyxl save)."""
    if not any(p.mcap is None or p.firm_pct is None for p in model):
        return model

    form_wb = openpyxl.load_workbook(path, read_only=True, data_only=False)
    try:
        if "Model" not in form_wb.sheetnames:
            return model
        form_by_symbol: dict[str, Any] = {}
        for row in form_wb["Model"].iter_rows(values_only=True):
            symbol = _symbol(row[0] if row else None)
            if symbol is None:
                continue
            form_by_symbol[symbol] = row
    finally:
        form_wb.close()

    out: list[ClientPortfolioPosition] = []
    for pos in model:
        mcap = pos.mcap
        firm = pos.firm_pct
        price = pos.excel_price or stocks_price.get(pos.symbol)
        form_row = form_by_symbol.get(pos.symbol)
        if mcap is None and form_row is not None:
            mcap = _mcap_from_formula(_cell(tuple(form_row), 6), price)
        if firm is None:
            firm = _firm_pct_from_parts(
                stocks_qty.get(pos.symbol), price, mcap
            )
        if mcap == pos.mcap and firm == pos.firm_pct:
            out.append(pos)
            continue
        out.append(
            ClientPortfolioPosition(
                symbol=pos.symbol,
                qty=pos.qty,
                excel_price=pos.excel_price if pos.excel_price is not None else price,
                excel_value=pos.excel_value,
                excel_percent=pos.excel_percent,
                index_label=pos.index_label,
                mcap=mcap,
                as_of_label=pos.as_of_label,
                firm_pct=firm,
                target_value=pos.target_value,
                portfolio_flag=pos.portfolio_flag,
                ramprasath_qty=pos.ramprasath_qty,
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
    """Pull Portfolio + BSESmallCap year blocks from the Model sheet layout."""
    series: list[YearlyReturnSeries] = []

    def add(name: str, year_col: int, block: list[tuple[Any, ...]]) -> None:
        parsed = _parse_year_block(block, year_col=year_col)
        if parsed:
            series.append(YearlyReturnSeries(name=name, rows=tuple(parsed)))

    mid_idx = next((i for i, row in enumerate(rows) if _is_midcap_header(row)), None)
    top = rows if mid_idx is None else rows[:mid_idx]

    # Header: Portfolio years @ col 11, BSESmallCap @ col 16/17
    add("Portfolio", 11, top)
    small_name = _label_at(rows[0], 16) if rows else None
    add(small_name or "BSESmallCap", 17, top)
    # MidCap / Sensex / BSE500 stay in Excel; UI only needs Portfolio + SmallCap.
    return series


def _rewrite_year_block_metrics(
    ws: Any,
    *,
    year_col: int,
    start_col: int,
    end_col: int,
    ret_col: int,
    cum_col: int,
    max_row: int,
) -> None:
    """Replace Return/Cum formulas with values so openpyxl save does not blank them."""
    rows: list[tuple[int, Decimal | None, Decimal | None]] = []
    first_start: Decimal | None = None
    for r in range(1, max_row + 1):
        if _as_year(ws.cell(r, year_col).value) is None:
            continue
        start = _to_decimal(ws.cell(r, start_col).value)
        end = _to_decimal(ws.cell(r, end_col).value)
        if first_start is None and start is not None:
            first_start = start
        rows.append((r, start, end))
    for r, start, end in rows:
        if start is not None and end is not None and start != 0:
            ws.cell(r, ret_col, float(end / start - 1))
        if first_start is not None and first_start != 0 and end is not None:
            ws.cell(r, cum_col, float(end / first_start - 1))


def write_bse_smallcap_year(
    *,
    year: int,
    start: Decimal | None = None,
    end: Decimal | None = None,
    path: Path | None = None,
) -> dict[str, float | int | None]:
    """Write Model BSESmallCap Start/End for ``year`` (cols R/S); refresh Return/Cum."""
    resolved = path or client_portfolio_write_path()
    if start is None and end is None:
        raise ValueError("Provide start and/or end")

    wb = openpyxl.load_workbook(resolved)
    try:
        if "Model" not in wb.sheetnames:
            raise FileNotFoundError("Model sheet missing")
        ws = wb["Model"]
        year_col = 18
        start_col, end_col, ret_col, cum_col = 19, 20, 21, 22
        mid_row = next(
            (
                r
                for r in range(1, (ws.max_row or 1) + 1)
                if _is_midcap_header(
                    tuple(ws.cell(r, c).value for c in range(1, max(ws.max_column or 1, 20) + 1))
                )
            ),
            (ws.max_row or 1) + 1,
        )
        row_i = next(
            (
                r
                for r in range(1, mid_row)
                if _as_year(ws.cell(r, year_col).value) == year
            ),
            None,
        )
        if row_i is None:
            raise ValueError(f"No BSESmallCap row for year {year}")

        if start is not None:
            ws.cell(row_i, start_col, float(start))
        if end is not None:
            ws.cell(row_i, end_col, float(end))

        _rewrite_year_block_metrics(
            ws,
            year_col=year_col,
            start_col=start_col,
            end_col=end_col,
            ret_col=ret_col,
            cum_col=cum_col,
            max_row=mid_row - 1,
        )
        _rewrite_year_block_metrics(
            ws,
            year_col=12,
            start_col=13,
            end_col=14,
            ret_col=15,
            cum_col=16,
            max_row=mid_row - 1,
        )

        start_v = _to_decimal(ws.cell(row_i, start_col).value)
        end_v = _to_decimal(ws.cell(row_i, end_col).value)

        _replace_save(wb, resolved)
        clear_client_portfolio_cache()
        return {
            "year": year,
            "start": float(start_v) if start_v is not None else None,
            "end": float(end_v) if end_v is not None else None,
        }
    finally:
        wb.close()


def _replace_save(wb: openpyxl.Workbook, resolved: Path) -> None:
    """Temp + replace: more reliable on Windows bind mounts than in-place save."""
    fd, tmp_name = tempfile.mkstemp(suffix=resolved.suffix, dir=resolved.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        wb.save(tmp)
        tmp.replace(resolved)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


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
    stocks_price: dict[str, Decimal] = {}
    for row in stocks_rows:
        if not row or row[0] is None:
            continue
        symbol = _symbol(row[0])
        if symbol is None:
            continue
        # Stocks: SYMBOL, name, price, blank, Quantity, Value
        price = _to_decimal(row[2] if len(row) > 2 else None)
        if price is not None:
            stocks_price[symbol] = price
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
            price = _to_decimal(_cell(row, 4))
            if price is not None:
                stocks_price[symbol] = price

    bank_balance: Decimal | None = None
    for row in quantity_rows:
        if not row or row[0] is None:
            continue
        if str(row[0]).strip().lower().replace(" ", "_") == "balance_with_bank":
            bank_balance = _to_decimal(_cell(row, 5))
            break

    model = _fill_missing_mcap_firm(
        model, path=path, stocks_qty=stocks_qty, stocks_price=stocks_price
    )

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
