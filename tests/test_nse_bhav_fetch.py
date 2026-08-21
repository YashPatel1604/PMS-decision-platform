"""NSE CM-UDiFF Final bhav download."""

from __future__ import annotations

import io
import zipfile
from datetime import date
from pathlib import Path

import httpx

from pms_platform.market_data.nse_bhav_fetch import (
    BhavFetchError,
    download_cm_udiff_bhav,
    udiff_zip_url,
)
from pms_platform.market_data.nse_bhav_parse import parse_bhav_file


def _zip_bytes_with_csv(csv_text: str, member: str = "BhavCopy_NSE_CM_0_0_0_20260820_F_0000.csv") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(member, csv_text)
    return buf.getvalue()


def test_udiff_zip_url() -> None:
    assert udiff_zip_url(date(2026, 8, 20)).endswith("BhavCopy_NSE_CM_0_0_0_20260820_F_0000.csv.zip")


def test_download_cm_udiff_extracts_csv(tmp_path: Path, monkeypatch) -> None:
    csv_text = (
        "TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,"
        "FinInstrmNm,OpnPric,HghPric,LwPric,ClsPric,PrvsClsgPric,TtlTradgVol,TtlTrfVal\n"
        "2026-08-20,2026-08-20,CM,NSE,STK,1,INE001A01036,RELIANCE,EQ,Reliance,"
        "1410,1430,1400,1425,1410,1100,1567500\n"
    )
    zip_bytes = _zip_bytes_with_csv(csv_text)

    class FakeResponse:
        def __init__(self, status_code: int, content: bytes = b"") -> None:
            self.status_code = status_code
            self.content = content

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url: str, timeout: float = 30.0):
            if "nseindia.com/all-reports" in url or url.rstrip("/").endswith("nseindia.com"):
                return FakeResponse(200, b"<html>")
            if "20260820" in url:
                return FakeResponse(200, zip_bytes)
            return FakeResponse(404, b"missing")

    monkeypatch.setattr(httpx, "Client", FakeClient)

    day, path = download_cm_udiff_bhav(date(2026, 8, 20), dest_dir=tmp_path)
    assert day == date(2026, 8, 20)
    assert path.is_file()
    rows = parse_bhav_file(path)
    assert len(rows) == 1
    assert rows[0].symbol == "RELIANCE"


def test_download_looks_back_only_when_requested(tmp_path: Path, monkeypatch) -> None:
    csv_text = (
        "TradDt,TckrSymb,SctySrs,OpnPric,HghPric,LwPric,ClsPric\n"
        "2026-08-19,INFY,EQ,100,110,90,105\n"
    )
    zip_bytes = _zip_bytes_with_csv(csv_text, "day.csv")

    class FakeResponse:
        def __init__(self, status_code: int, content: bytes = b"") -> None:
            self.status_code = status_code
            self.content = content

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url: str, timeout: float = 30.0):
            if "nseindia.com" in url and "BhavCopy" not in url:
                return FakeResponse(200, b"ok")
            if "20260819" in url:
                return FakeResponse(200, zip_bytes)
            return FakeResponse(404, b"missing")

    monkeypatch.setattr(httpx, "Client", FakeClient)
    monkeypatch.setattr(
        "pms_platform.market_data.nse_bhav_fetch.today_ist",
        lambda: date(2026, 8, 20),
    )

    try:
        download_cm_udiff_bhav(dest_dir=tmp_path, lookback_days=0)
        raise AssertionError("expected BhavFetchError without lookback")
    except BhavFetchError as exc:
        assert "not published yet" in str(exc)

    day, path = download_cm_udiff_bhav(dest_dir=tmp_path, lookback_days=3)
    assert day == date(2026, 8, 19)
    assert parse_bhav_file(path)[0].symbol == "INFY"


def test_download_raises_when_all_missing(tmp_path: Path, monkeypatch) -> None:
    class FakeResponse:
        status_code = 404
        content = b"x"

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url: str, timeout: float = 30.0):
            return FakeResponse()

    monkeypatch.setattr(httpx, "Client", FakeClient)
    try:
        download_cm_udiff_bhav(date(2026, 8, 20), dest_dir=tmp_path)
        raise AssertionError("expected BhavFetchError")
    except BhavFetchError:
        pass


def test_has_bhav_trade_date_after_sync(session, tmp_path, monkeypatch) -> None:
    from pms_platform.market_data.nse_bhav_store import has_bhav_trade_date, sync_bhav_file

    monkeypatch.setattr(
        "pms_platform.market_data.nse_bhav_store.settings.upload_dir",
        tmp_path,
    )
    fixture = Path(__file__).parent / "fixtures" / "pivot" / "bhav_2026-08-19.csv"
    assert not has_bhav_trade_date(session, date(2026, 8, 19))
    sync_bhav_file(session, fixture)
    session.commit()
    assert has_bhav_trade_date(session, date(2026, 8, 19))
    assert not has_bhav_trade_date(session, date(2026, 8, 20))
