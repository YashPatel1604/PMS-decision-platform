"""Client Portfolio workbook parse + bhav join."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from pms_platform.market_data.client_portfolio_dashboard import (
    build_client_portfolio_dashboard,
)
from pms_platform.market_data.client_portfolio_parse import (
    clear_client_portfolio_cache,
    parse_client_portfolio_workbook,
)
from pms_platform.market_data.nse_bhav_store import sync_bhav_file, upsert_portfolio_symbols
from pms_platform.market_data.pivot_derived import floor_pivot_levels

FIXTURES = Path(__file__).parent / "fixtures" / "pivot"
BOOK = FIXTURES / "PMS_ClientPortfolio_fixture.xlsx"


def test_parse_client_portfolio_model_and_stocks() -> None:
    book = parse_client_portfolio_workbook(BOOK)
    assert book.excel_total_value == Decimal("44305")
    by_sym = {p.symbol: p for p in book.model}
    assert set(by_sym) == {"RELIANCE", "INFY", "NOSUCH"}
    assert by_sym["RELIANCE"].qty == Decimal(10)
    assert book.stocks_qty["RELIANCE"] == Decimal(100)


def test_client_portfolio_dashboard_joins_bhav(session, tmp_path, monkeypatch) -> None:
    clear_client_portfolio_cache()
    monkeypatch.setattr(
        "pms_platform.market_data.nse_bhav_store.settings.upload_dir",
        str(tmp_path),
    )
    monkeypatch.setattr(
        "pms_platform.market_data.client_portfolio_dashboard.load_client_portfolio_book",
        lambda path=None: parse_client_portfolio_workbook(BOOK),
    )
    sync_bhav_file(session, FIXTURES / "bhav_2026-08-19.csv")
    upsert_portfolio_symbols(session, [{"symbol": "RELIANCE", "portfolio_a": True}])
    session.commit()

    dash = build_client_portfolio_dashboard(session, as_of=date(2026, 8, 19))
    assert dash["error"] is None
    assert dash["as_of"] == "2026-08-19"
    by_sym = {r["symbol"]: r for r in dash["holdings"]}
    rel = by_sym["RELIANCE"]
    assert rel["missing_bhav"] is False
    assert rel["close"] == 1425.0
    assert rel["qty"] == 10.0
    assert abs(rel["bhav_value"] - 14250.0) < 1e-6
    assert rel["qty_mismatch"] is True  # Model 10 vs Stocks 100
    levels = floor_pivot_levels(Decimal("1430"), Decimal("1400"), Decimal("1425"))
    assert abs(rel["pivot"]["pp"] - float(levels["pp"])) < 1e-9
    assert abs(rel["pivot"]["s4_03"] - float(levels["s4_03"])) < 1e-9
    assert by_sym["NOSUCH"]["missing_bhav"] is True
    assert "NOSUCH" in dash["missing_symbols"]
