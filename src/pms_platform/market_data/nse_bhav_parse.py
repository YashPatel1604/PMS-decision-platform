"""Parse NSE CM UDiFF bhav CSV/XLSX into normalized bar dicts."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

REQUIRED_COLUMNS = (
    "TradDt",
    "TckrSymb",
    "SctySrs",
    "OpnPric",
    "HghPric",
    "LwPric",
    "ClsPric",
)


@dataclass(frozen=True)
class ParsedBhavRow:
    trade_date: date
    symbol: str
    series: str
    isin: str | None
    instrument_name: str | None
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    prev_close: Decimal | None
    volume: int
    turnover: Decimal | None

    @property
    def source_key(self) -> str:
        return f"{self.trade_date.isoformat()}|{self.symbol}|{self.series}"


class BhavParseError(ValueError):
    """Raised when a bhav file cannot be parsed."""


def _dec(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def _int(value: object) -> int:
    if value is None or value == "":
        return 0
    try:
        return int(Decimal(str(value).strip().replace(",", "")))
    except (InvalidOperation, ValueError, TypeError):
        return 0


def _parse_date(value: object) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    if "T" in text:
        text = text.split("T", 1)[0]
    if " " in text:
        text = text.split(" ", 1)[0]
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:11].strip(), fmt).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(text[:10])
    except ValueError as exc:
        raise BhavParseError(f"Unparseable TradDt: {value!r}") from exc


def _norm_header(name: object) -> str:
    return str(name or "").strip()


def _row_get(row: dict[str, Any], *names: str) -> object:
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    lower = {str(k).strip().lower(): v for k, v in row.items()}
    for name in names:
        hit = lower.get(name.lower())
        if hit not in (None, ""):
            return hit
    return None


def normalize_bhav_row(raw: dict[str, Any]) -> ParsedBhavRow | None:
    """Map one raw UDiFF-like dict to ParsedBhavRow. Returns None for blank symbol."""
    symbol = str(_row_get(raw, "TckrSymb", "SYMBOL", "Symbol") or "").strip().upper()
    if not symbol:
        return None
    series = str(_row_get(raw, "SctySrs", "SERIES", "Series") or "EQ").strip().upper() or "EQ"
    trade_date = _parse_date(_row_get(raw, "TradDt", "TIMESTAMP", "DATE", "BizDt"))
    if trade_date is None:
        raise BhavParseError(f"Missing TradDt for {symbol}")
    open_ = _dec(_row_get(raw, "OpnPric", "OPEN", "Open"))
    high = _dec(_row_get(raw, "HghPric", "HIGH", "High"))
    low = _dec(_row_get(raw, "LwPric", "LOW", "Low"))
    close = _dec(_row_get(raw, "ClsPric", "CLOSE", "Close"))
    if open_ is None or high is None or low is None or close is None:
        raise BhavParseError(f"Missing OHLC for {symbol} on {trade_date}")
    return ParsedBhavRow(
        trade_date=trade_date,
        symbol=symbol,
        series=series,
        isin=(str(_row_get(raw, "ISIN") or "").strip().upper() or None),
        instrument_name=(str(_row_get(raw, "FinInstrmNm", "SECURITY") or "").strip() or None),
        open=open_,
        high=high,
        low=low,
        close=close,
        prev_close=_dec(_row_get(raw, "PrvsClsgPric", "PREVCLOSE", "Prev Close")),
        volume=_int(_row_get(raw, "TtlTradgVol", "TOTTRDQTY", "Volume")),
        turnover=_dec(_row_get(raw, "TtlTrfVal", "TOTTRDVAL", "Turnover")),
    )


def _read_tabular(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".txt"}:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise BhavParseError("CSV has no header")
            return [{_norm_header(k): v for k, v in row.items()} for row in reader]
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        from openpyxl import load_workbook

        wb = load_workbook(path, read_only=True, data_only=True)
        # Prefer sheet named Daily; else first sheet.
        ws = wb["Daily"] if "Daily" in wb.sheetnames else wb[wb.sheetnames[0]]
        rows_iter = ws.iter_rows(values_only=True)
        try:
            header_row = next(rows_iter)
        except StopIteration as exc:
            wb.close()
            raise BhavParseError("Workbook is empty") from exc
        headers = [_norm_header(h) for h in header_row]
        out: list[dict[str, Any]] = []
        for values in rows_iter:
            if values is None or all(v is None or v == "" for v in values):
                continue
            out.append({headers[i]: values[i] for i in range(min(len(headers), len(values)))})
        wb.close()
        return out
    raise BhavParseError(f"Unsupported bhav file type: {suffix}")


def parse_bhav_file(path: Path) -> list[ParsedBhavRow]:
    """Parse a daily NSE CM bhav file into normalized rows."""
    path = Path(path)
    if not path.is_file():
        raise BhavParseError(f"File not found: {path}")
    raw_rows = _read_tabular(path)
    if not raw_rows:
        raise BhavParseError("No data rows in bhav file")
    headers = set(raw_rows[0].keys())
    missing = [c for c in REQUIRED_COLUMNS if c not in headers and c.lower() not in {h.lower() for h in headers}]
    # Allow legacy NSE headers via normalize aliases — only require after alias check on first row.
    parsed: list[ParsedBhavRow] = []
    for raw in raw_rows:
        try:
            row = normalize_bhav_row(raw)
        except BhavParseError:
            # Skip garbage rows that lack OHLC when symbol blank already None
            if not str(_row_get(raw, "TckrSymb", "SYMBOL", "Symbol") or "").strip():
                continue
            raise
        if row is not None:
            parsed.append(row)
    if not parsed:
        raise BhavParseError("No parseable bhav rows")
    if missing and not any(
        _row_get(raw_rows[0], "SYMBOL", "Symbol", "TckrSymb") for _ in [0]
    ):
        raise BhavParseError(f"Missing columns: {missing}")
    return parsed
