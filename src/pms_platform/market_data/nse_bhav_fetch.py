"""Download NSE CM-UDiFF Common Bhavcopy Final from nsearchives."""

from __future__ import annotations

import io
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.orm import Session

from pms_platform.config import settings

_IST = ZoneInfo("Asia/Kolkata")
_ZIP_URL = (
    "https://nsearchives.nseindia.com/content/cm/"
    "BhavCopy_NSE_CM_0_0_0_{stamp}_F_0000.csv.zip"
)
_NSE_HOME = "https://www.nseindia.com/"
_NSE_REPORTS = "https://www.nseindia.com/all-reports"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": _NSE_REPORTS,
}


class BhavFetchError(RuntimeError):
    """Raised when the NSE Final bhav zip cannot be downloaded."""


def today_ist() -> date:
    return datetime.now(_IST).date()


def udiff_zip_url(trade_date: date) -> str:
    return _ZIP_URL.format(stamp=trade_date.strftime("%Y%m%d"))


def _bhav_dest_dir() -> Path:
    path = Path(settings.upload_dir) / "bhav" / "nse"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _extract_csv(zip_bytes: bytes, dest_dir: Path) -> Path:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not names:
            raise BhavFetchError("Zip has no CSV member")
        name = names[0]
        out = dest_dir / Path(name).name
        out.write_bytes(zf.read(name))
        return out


def _try_download(client: httpx.Client, trade_date: date, dest_dir: Path) -> Path | None:
    url = udiff_zip_url(trade_date)
    response = client.get(url, timeout=90.0)
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise BhavFetchError(f"NSE returned HTTP {response.status_code} for {url}")
    if response.content[:2] != b"PK":
        raise BhavFetchError(f"NSE response is not a zip for {trade_date.isoformat()}")
    return _extract_csv(response.content, dest_dir)


def download_cm_udiff_bhav(
    trade_date: date | None = None,
    *,
    dest_dir: Path | None = None,
    lookback_days: int = 0,
) -> tuple[date, Path]:
    """Download CM-UDiFF Common Bhavcopy Final and extract the CSV.

    Defaults to **today (IST) only**. Set ``lookback_days`` > 0 only for
    intentional backfill — scheduled jobs must not silently load an older day.
    """
    dest = Path(dest_dir) if dest_dir is not None else _bhav_dest_dir()
    dest.mkdir(parents=True, exist_ok=True)

    if trade_date is not None:
        candidates = [trade_date]
        if lookback_days > 0:
            candidates.extend(
                trade_date - timedelta(days=i) for i in range(1, lookback_days + 1)
            )
    else:
        start = today_ist()
        candidates = [start - timedelta(days=i) for i in range(lookback_days + 1)]

    with httpx.Client(headers=_HEADERS, follow_redirects=True, timeout=90.0) as client:
        # Cookie warm-up — NSE archives often 403 without a prior www hit.
        try:
            client.get(_NSE_HOME, timeout=30.0)
            client.get(_NSE_REPORTS, timeout=30.0)
        except httpx.HTTPError:
            pass
        last_error: Exception | None = None
        for day in candidates:
            try:
                path = _try_download(client, day, dest)
            except BhavFetchError as exc:
                last_error = exc
                continue
            except httpx.HTTPError as exc:
                last_error = BhavFetchError(str(exc))
                continue
            if path is not None:
                return day, path
        if last_error is not None:
            raise last_error
        target = candidates[0].isoformat()
        raise BhavFetchError(
            f"CM-UDiFF Final bhav not published yet for {target} IST. "
            "Upload the zip on Pivot Point Strategy."
        )


def fetch_and_commit_cm_udiff_bhav(
    session: Session,
    trade_date: date | None = None,
    *,
    lookback_days: int = 0,
) -> dict[str, object]:
    """Download today's (IST) Final bhav and commit, or skip if already present.

    Returns a small dict for CLI/API: skipped, trade_date, message, run fields.
    """
    from pms_platform.market_data.nse_bhav_store import has_bhav_trade_date, sync_bhav_file

    target = trade_date or today_ist()
    if has_bhav_trade_date(session, target):
        return {
            "skipped": True,
            "trade_date": target,
            "message": (
                f"{target.isoformat()} IST already committed "
                "(manual upload or earlier pull)."
            ),
            "run_id": None,
            "status": "skipped",
            "row_count_all": None,
            "row_count_eq": None,
        }

    day, path = download_cm_udiff_bhav(trade_date, lookback_days=lookback_days)
    if has_bhav_trade_date(session, day):
        return {
            "skipped": True,
            "trade_date": day,
            "message": (
                f"{day.isoformat()} IST already committed while download was in flight."
            ),
            "run_id": None,
            "status": "skipped",
            "row_count_all": None,
            "row_count_eq": None,
        }

    run = sync_bhav_file(session, path)
    session.flush()
    ok = run.status == "committed"
    return {
        "skipped": False,
        "trade_date": run.trade_date or day,
        "message": (
            f"Committed {run.trade_date}: {run.row_count_all} rows "
            f"({run.row_count_eq} EQ)."
            if ok
            else (run.error_message or f"Bhav run status={run.status}")
        ),
        "run_id": run.run_id,
        "status": run.status,
        "row_count_all": run.row_count_all,
        "row_count_eq": run.row_count_eq,
    }
