"""Charts Range sheet parse + bhav join."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook

from pms_platform.market_data.charts_dashboard import (
    build_charts_dashboard,
    parse_charts_range,
    write_charts_range_weekly,
)
from pms_platform.market_data.nse_bhav_store import sync_bhav_file

FIXTURES = Path(__file__).parent / "fixtures" / "pivot"


def _range_book(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Range "
    ws.append(["Name", "High", "Low"])
    ws.append([None, None, "Check lows support"])
    ws.append(
        [
            "Reliance",
            1600,
            1000,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            '=VLOOKUP(A3&"EQ",BhavCopy_NSE_CM!A:U,19,0)',
        ]
    )
    ws.append(["NIFTY FNO STOCKS"])
    ws.append(["TCS", 4000, 3000])
    wb.save(path)
    wb.close()


def test_parse_charts_range_reads_names(tmp_path: Path) -> None:
    path = tmp_path / "Charts - Copy.xlsx"
    _range_book(path)
    rows = parse_charts_range(path)
    assert [r["symbol"] for r in rows] == ["RELIANCE", "TCS"]
    assert rows[0]["section"] == "holdings"
    assert rows[1]["section"] == "fno"
    assert rows[0]["high"] == Decimal("1600")
    assert rows[0]["series"] == "EQ"
    assert rows[0]["excel_row"] == 3


def test_write_charts_range_weekly_holdings_only(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "Charts - Copy.xlsx"
    _range_book(path)
    monkeypatch.setattr(
        "pms_platform.market_data.charts_dashboard.charts_workbook_path",
        lambda folder=None: path,
    )
    written = write_charts_range_weekly(
        3,
        weekly_close=1410.5,
        support_resistance="S",
        weekly_close_date="22.08.2026",
    )
    assert written["weekly_close"] == 1410.5
    rows = parse_charts_range(path)
    assert rows[0]["weekly_close"] == Decimal("1410.5")
    assert rows[0]["support_resistance"] == "S"
    assert rows[0]["weekly_close_date"] == "22.08.2026"
    try:
        write_charts_range_weekly(5, weekly_close=1, support_resistance="R", weekly_close_date=None)
        raise AssertionError("FNO row should reject")
    except ValueError:
        pass


def test_charts_dashboard_joins_bhav(session, tmp_path, monkeypatch) -> None:
    path = tmp_path / "Charts - Copy.xlsx"
    _range_book(path)
    monkeypatch.setattr(
        "pms_platform.market_data.nse_bhav_store.settings.upload_dir",
        str(tmp_path),
    )
    monkeypatch.setattr(
        "pms_platform.market_data.charts_dashboard.charts_workbook_path",
        lambda folder=None: path,
    )
    sync_bhav_file(session, FIXTURES / "bhav_2026-08-19.csv")
    session.commit()

    dash = build_charts_dashboard(session, as_of=date(2026, 8, 19))
    assert dash["error"] is None
    rel = dash["rows"][0]
    assert rel["section"] == "holdings"
    assert dash["rows"][1]["section"] == "fno"
    assert rel["symbol"] == "RELIANCE"
    assert rel["close"] == 1425.0
    assert rel["difference"] == 600.0
    assert abs(rel["trg_13"] - 1078.0) < 1e-6
    assert abs(rel["pct_from_lows"] - 42.5) < 1e-6
    assert rel["below_trg_89"] is True
    assert rel["missing_bhav"] is False
