"""Client Portfolio dashboard: Excel Model qty × Pivot bhav OHLC/pivots/Vol Exp."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from pms_platform.market_data.client_portfolio_parse import (
    book_meta,
    load_client_portfolio_book,
    yearly_as_dicts,
)
from pms_platform.market_data.nse_bhav_store import (
    available_trade_dates,
    load_day_bars,
    load_vol_exp_map,
)
from pms_platform.market_data.pivot_derived import FloorPivot, floor_pivot_levels
from pms_platform.market_data.pivot_dashboard import DAILY_SERIES, latest_committed_run


def _pivot_from_bar(bar: Any, *, as_of: date) -> dict[str, Any]:
    levels = floor_pivot_levels(bar.high, bar.low, bar.close)
    return FloorPivot(
        symbol=bar.symbol,
        series=bar.series,
        as_of=as_of,
        prior_date=bar.trade_date,
        prior_high=bar.high,
        prior_low=bar.low,
        prior_close=bar.close,
        last_close=bar.close,
        missing=False,
        **levels,
    ).as_dict()


def _pick_bar(eq_map: dict[str, Any], be_map: dict[str, Any], symbol: str) -> Any | None:
    return eq_map.get(symbol) or be_map.get(symbol)


def _fill_ramprasath(row: dict[str, Any], pos: Any) -> None:
    """Quantity G/H/I: G=D−H, H static Ramprasath qty, I=H×price."""
    rp = pos.ramprasath_qty
    if rp is None:
        return
    row["ramprasath_qty"] = float(rp)
    row["ex_ramprasath_qty"] = float(pos.qty - rp)
    if row.get("price") is not None:
        row["blocked_value"] = float(rp * Decimal(str(row["price"])))


def _patch_portfolio_ytd(
    yearly: list[dict[str, Any]], *, year: int, total: float
) -> list[dict[str, Any]]:
    """Set Portfolio current-year End / Return / Cum from live Total_Value."""
    for series in yearly:
        if series.get("name") != "Portfolio":
            continue
        rows = series.get("rows") or []
        if not rows:
            continue
        target = next((r for r in rows if r.get("year") == year), rows[-1])
        start = target.get("start")
        initial = rows[0].get("start")
        target["end"] = total
        if start and start != 0:
            target["return_pct"] = (total / start - 1.0) * 100.0
        if initial and initial != 0:
            target["cum_pct"] = (total / initial - 1.0) * 100.0
    return yearly


def build_client_portfolio_dashboard(
    session: Session,
    *,
    as_of: date | None = None,
    book: str = "client",
) -> dict[str, Any]:
    dates = available_trade_dates(session)
    if as_of is None:
        as_of = dates[0] if dates else None

    book_key = (book or "client").strip().lower()
    if book_key == "sca":
        from pms_platform.market_data.daily_edit_bhav import sca_llp_workbook_path

        source_path = sca_llp_workbook_path()
        loaded = load_client_portfolio_book(source_path) if source_path else None
        missing_msg = (
            "SCA_LLP Stock Holding.xlsx not found under DailyEditFiles "
            "(set DAILY_EDIT_DIR / pin Always keep on this device)."
        )
    else:
        loaded = load_client_portfolio_book()
        missing_msg = (
            "PMS_ClientPortfolio.xlsx not found under Research/Portfolio "
            "(pin Always keep on this device)."
        )

    empty = {
        "as_of": as_of.isoformat() if as_of else None,
        "available_dates": [d.isoformat() for d in dates],
        "book": book_key,
        "source_file": None,
        "excel_mtime": None,
        "excel_total_value": None,
        "bank_balance": None,
        "portfolio_total": None,
        "bhav_revalued_total": None,
        "total_value": None,
        "holdings": [],
        "yearly": [],
        "missing_symbols": [],
        "model_symbols": [],
        "error": None,
    }
    if loaded is None:
        empty["error"] = missing_msg
        return empty
    if as_of is None:
        meta = book_meta(loaded)
        empty.update(meta)
        empty["total_value"] = meta["excel_total_value"]
        empty["model_symbols"] = [p.symbol for p in loaded.model]
        empty["yearly"] = yearly_as_dicts(loaded)
        if book_key == "sca":
            empty["bank_balance"] = meta.get("bank_balance")
            empty["portfolio_total"] = (meta.get("excel_total_value") or 0) + (
                meta.get("bank_balance") or 0
            )
        empty["error"] = "No bhav days committed yet — upload on Pivot Point Strategy."
        return empty

    eq_bars = {b.symbol: b for b in load_day_bars(session, as_of, series="EQ")}
    be_bars = {b.symbol: b for b in load_day_bars(session, as_of, series="BE")}
    vol_exp_by_symbol = load_vol_exp_map(session, as_of)

    holdings: list[dict[str, Any]] = []
    missing: list[str] = []

    for pos in loaded.model:
        bar = _pick_bar(eq_bars, be_bars, pos.symbol)
        stocks_qty = loaded.stocks_qty.get(pos.symbol)
        qty_mismatch = stocks_qty is not None and stocks_qty != pos.qty
        excel_price = float(pos.excel_price) if pos.excel_price is not None else None
        excel_value = float(pos.excel_value) if pos.excel_value is not None else None

        row: dict[str, Any] = {
            "symbol": pos.symbol,
            "qty": float(pos.qty),
            "stocks_qty": float(stocks_qty) if stocks_qty is not None else None,
            "qty_mismatch": qty_mismatch,
            "excel_price": excel_price,
            "excel_value": excel_value,
            "excel_percent": float(pos.excel_percent)
            if pos.excel_percent is not None
            else None,
            "index_label": pos.index_label,
            "mcap": float(pos.mcap) if pos.mcap is not None else None,
            "as_of_label": pos.as_of_label,
            "firm_pct": float(pos.firm_pct) if pos.firm_pct is not None else None,
            "target_value": float(pos.target_value) if pos.target_value is not None else None,
            "portfolio_flag": pos.portfolio_flag,
            "ramprasath_qty": None,
            "ex_ramprasath_qty": None,
            "blocked_value": None,
            "series": None,
            "close": None,
            "bhav_value": None,
            "price": excel_price,
            "value": excel_value,
            "percent": None,
            "be_only": False,
            "missing_bhav": bar is None,
            "pivot": None,
            "vol_exp": None,
            "vol_15min": None,
            "top50": None,
            "band_51_300": None,
        }

        if bar is None or bar.series not in DAILY_SERIES:
            if bar is not None and bar.series not in DAILY_SERIES:
                missing.append(pos.symbol)
            elif bar is None:
                missing.append(pos.symbol)
            _fill_ramprasath(row, pos)
            holdings.append(row)
            continue

        close = Decimal(bar.close)
        bhav_value = pos.qty * close
        vol_exp = vol_exp_by_symbol.get(pos.symbol)
        row.update(
            {
                "series": bar.series,
                "close": float(close),
                "bhav_value": float(bhav_value),
                "price": float(close),
                "value": float(bhav_value),
                "be_only": bar.series == "BE",
                "missing_bhav": False,
                "pivot": _pivot_from_bar(bar, as_of=as_of),
            }
        )
        if vol_exp is not None:
            vol_15 = Decimal(vol_exp) / Decimal(25)
            row["vol_exp"] = float(vol_exp)
            row["vol_15min"] = float(vol_15)
            row["top50"] = float(vol_15 * Decimal(3))
            row["band_51_300"] = float(vol_15 * Decimal(6))
        _fill_ramprasath(row, pos)
        holdings.append(row)

    total = Decimal(0)
    for row in holdings:
        if row["value"] is not None:
            total += Decimal(str(row["value"]))
    total_f = float(total) if holdings else None
    if total_f and total_f != 0:
        for row in holdings:
            if row["value"] is not None:
                row["percent"] = float(Decimal(str(row["value"])) / total * Decimal(100))

    yearly = _patch_portfolio_ytd(
        yearly_as_dicts(loaded), year=as_of.year, total=total_f or 0.0
    )

    run = latest_committed_run(session, as_of)
    last_run = None
    if run is not None:
        last_run = {
            "run_id": run.run_id,
            "trade_date": run.trade_date.isoformat() if run.trade_date else None,
            "status": run.status,
            "source_filename": run.source_filename,
        }

    meta = book_meta(loaded)
    qty_src = (
        "Quantity!Total Quantity from DailyEditFiles SCA_LLP"
        if book_key == "sca"
        else "Model!Qnty from Research PMS_ClientPortfolio.xlsx"
    )
    bank = (
        float(loaded.bank_balance)
        if book_key == "sca" and loaded.bank_balance is not None
        else None
    )
    portfolio_total = None
    if book_key == "sca" and (total_f is not None or bank is not None):
        portfolio_total = (total_f or 0.0) + (bank or 0.0)
    return {
        "as_of": as_of.isoformat(),
        "available_dates": [d.isoformat() for d in dates],
        "book": book_key,
        "source_file": meta["source_file"],
        "excel_mtime": meta["excel_mtime"],
        "excel_total_value": meta["excel_total_value"],
        "bank_balance": bank,
        "portfolio_total": portfolio_total,
        "bhav_revalued_total": total_f,
        "total_value": total_f,
        "holdings": holdings,
        "yearly": yearly,
        "missing_symbols": missing,
        "model_symbols": [p.symbol for p in loaded.model],
        "last_run": last_run,
        "error": None,
        "formulas": {
            "qty": qty_src,
            "price_value_percent": "Price/Value/Percent/Total_Value from qty × as-of bhav close",
            "yearly_portfolio": "Portfolio current year End/Return/Cum updated from Total_Value",
            "yearly_benchmarks": "BSESmallCap / MidCap / Sensex / BSE500 stay from workbook",
            "ramprasath": "Quantity!H Ramprasath qty is static; G=D−H; I=H×as-of price",
            "bank": "Quantity!F Balance with Bank is typed; Total Portfolio = Total_Value + bank",
        },
    }
