"""Parse Research/Portfolio/PMS_ClientPortfolio.xlsx (Model + Stocks).

Read-only. Never writes back into Research.
"""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class ClientPortfolioBook:
    path: Path
    mtime: float
    model: list[ClientPortfolioPosition]
    stocks_qty: dict[str, Decimal]
    excel_total_value: Decimal | None


def client_portfolio_workbook_path() -> Path | None:
    portfolio = research_portfolio_dir()
    if portfolio is None:
        return None
    path = portfolio / "PMS_ClientPortfolio.xlsx"
    return path if path.is_file() else None


def _to_decimal(raw: object) -> Decimal | None:
    if raw is None or raw == "":
        return None
    try:
        return Decimal(str(raw).strip().replace(",", ""))
    except Exception:  # noqa: BLE001
        return None


def _symbol(raw: object) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip().upper()
    if not text or text.lower().replace(" ", "_") in _SKIP:
        return None
    return text


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
    finally:
        workbook.close()

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
        model.append(
            ClientPortfolioPosition(
                symbol=symbol,
                qty=qty,
                excel_price=_to_decimal(row[2] if len(row) > 2 else None),
                excel_value=_to_decimal(row[3] if len(row) > 3 else None),
                excel_percent=_to_decimal(row[4] if len(row) > 4 else None),
                index_label=(
                    str(row[5]).strip()
                    if len(row) > 5 and row[5] not in (None, "")
                    else None
                ),
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

    return ClientPortfolioBook(
        path=path,
        mtime=mtime,
        model=model,
        stocks_qty=stocks_qty,
        excel_total_value=excel_total,
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
        "model_count": len(book.model),
    }
