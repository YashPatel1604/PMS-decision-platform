"""Repair back-adjusted daily prices from Yahoo Finance.

EOD2 historical series is split/bonus adjusted but often misses rights (and
occasional vendor scale bugs). STOCK% uses adjusted_close, so a missing rights
back-adjust understates long-held returns (Heritage: ~4.5x vs ~10x).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.market_data.yahoo_finance import YahooFinanceClient
from pms_platform.models import DailyPrice, ImportBatch, Security

_SEED_SOURCE = "EOD2_NSE_ADJUSTED"
_REPAIR_SOURCE_TAG = "YAHOO_CHART_REPAIR"
_LIVE_SOURCES = frozenset({"YAHOO_FINANCE", "INDIAN_STOCK_API"})


@dataclass(frozen=True)
class PriceRepairResult:
    security_id: str
    portfolio_name: str
    yahoo_ticker: str
    bars_fetched: int
    rows_updated: int
    rows_inserted: int
    csv_rows_rewritten: int


def _yahoo_tickers_for(security: Security) -> list[str]:
    tickers: list[str] = []
    if security.current_nse_symbol:
        tickers.append(f"{security.current_nse_symbol}.NS")
    if (
        security.historical_nse_symbol
        and security.historical_nse_symbol != security.current_nse_symbol
    ):
        tickers.append(f"{security.historical_nse_symbol}.NS")
    if security.bse_code:
        tickers.append(f"{security.bse_code}.BO")
    return tickers


def _resolve_security(
    session: Session, *, security_id: str | None, portfolio_name: str | None
) -> Security:
    if security_id:
        sec = session.get(Security, security_id)
        if sec is None:
            raise ValueError(f"Unknown security_id: {security_id}")
        return sec
    if portfolio_name:
        sec = session.scalar(
            select(Security).where(Security.portfolio_name == portfolio_name)
        )
        if sec is None:
            raise ValueError(f"Unknown portfolio_name: {portfolio_name}")
        return sec
    raise ValueError("Provide security_id or portfolio_name")


def repair_security_prices_from_yahoo(
    session: Session,
    *,
    security_id: str | None = None,
    portfolio_name: str | None = None,
    start: date = date(2012, 1, 1),
    end: date | None = None,
    client: YahooFinanceClient | None = None,
    seed_csv: Path | None = None,
) -> PriceRepairResult:
    """Overwrite historical prices for one security with Yahoo chart bars."""
    sec = _resolve_security(session, security_id=security_id, portfolio_name=portfolio_name)
    end = end or date.today()
    yahoo = client or YahooFinanceClient()
    bars = []
    used = ""
    for ticker in _yahoo_tickers_for(sec):
        try:
            bars = yahoo.fetch_chart_bars(ticker, start, end)
        except Exception:
            bars = []
        if bars:
            used = ticker
            break
    if not bars:
        raise RuntimeError(f"No Yahoo bars for {sec.portfolio_name} ({sec.security_id})")

    batch = ImportBatch(
        source_type="daily_prices_yahoo_repair",
        source_file=f"yahoo:{used}",
        source_checksum=f"{used}:{start.isoformat()}:{end.isoformat()}:{len(bars)}",
        status="completed",
    )
    session.add(batch)
    session.flush()

    existing = session.scalars(
        select(DailyPrice).where(
            DailyPrice.security_id == sec.security_id,
            DailyPrice.trade_date >= start,
            DailyPrice.trade_date <= end,
        )
    ).all()
    by_date: dict[date, list[DailyPrice]] = {}
    for row in existing:
        by_date.setdefault(row.trade_date, []).append(row)

    updated = 0
    inserted = 0
    publication = date.today()
    for bar in bars:
        candidates = by_date.get(bar.trade_date, [])
        # Prefer non-live vendor rows so live quotes remain distinct.
        target = next(
            (r for r in candidates if r.source not in _LIVE_SOURCES),
            candidates[0] if candidates else None,
        )
        if target is not None:
            target.close = bar.close
            target.adjusted_close = bar.adjusted_close
            target.adjustment_basis = "SPLIT_AND_DIVIDEND"
            if bar.volume is not None:
                target.volume = bar.volume
            target.source = _SEED_SOURCE
            target.publication_date = publication
            updated += 1
        else:
            source_key = (
                f"yahoo_repair|{sec.security_id}|{bar.trade_date.isoformat()}|{used}"
            )
            session.add(
                DailyPrice(
                    security_id=sec.security_id,
                    identifier_type="SECURITY_ID",
                    identifier=sec.security_id,
                    trade_date=bar.trade_date,
                    close=bar.close,
                    adjusted_close=bar.adjusted_close,
                    adjustment_basis="SPLIT_AND_DIVIDEND",
                    volume=bar.volume,
                    currency="INR",
                    source=_SEED_SOURCE,
                    publication_date=publication,
                    source_file=f"yahoo:{used}",
                    source_row=0,
                    source_key=source_key,
                    import_batch_id=batch.import_batch_id,
                )
            )
            inserted += 1

    csv_rewritten = 0
    if seed_csv is not None and seed_csv.exists():
        csv_rewritten = _rewrite_seed_csv(seed_csv, sec, bars, used)

    session.flush()
    return PriceRepairResult(
        security_id=sec.security_id,
        portfolio_name=sec.portfolio_name,
        yahoo_ticker=used,
        bars_fetched=len(bars),
        rows_updated=updated,
        rows_inserted=inserted,
        csv_rows_rewritten=csv_rewritten,
    )


def _fmt_dec(value: Decimal | None) -> str:
    if value is None:
        return ""
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text if text else "0"


def _rewrite_seed_csv(
    path: Path, security: Security, bars: list, yahoo_ticker: str
) -> int:
    """Replace OHLC/adj/volume for one security_id in the canonical seed CSV."""
    by_date = {bar.trade_date.isoformat(): bar for bar in bars}
    retrieved = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    tmp = path.with_suffix(path.suffix + ".tmp")
    rewritten = 0
    with path.open(newline="", encoding="utf-8") as src, tmp.open(
        "w", newline="", encoding="utf-8"
    ) as dst:
        reader = csv.DictReader(src)
        if reader.fieldnames is None:
            raise ValueError(f"No header in {path}")
        writer = csv.DictWriter(dst, fieldnames=reader.fieldnames)
        writer.writeheader()
        for row in reader:
            if row.get("security_id") == security.security_id:
                bar = by_date.get(row.get("trade_date") or "")
                if bar is not None:
                    if "open" in row and bar.open is not None:
                        row["open"] = _fmt_dec(bar.open)
                    if "high" in row and bar.high is not None:
                        row["high"] = _fmt_dec(bar.high)
                    if "low" in row and bar.low is not None:
                        row["low"] = _fmt_dec(bar.low)
                    row["close"] = _fmt_dec(bar.close)
                    row["adjusted_close"] = _fmt_dec(bar.adjusted_close)
                    if bar.volume is not None and "volume" in row:
                        row["volume"] = str(bar.volume)
                    if "adjustment_scope" in row:
                        row["adjustment_scope"] = "SPLIT_BONUS_RIGHTS_DIV"
                    if "source" in row:
                        row["source"] = _REPAIR_SOURCE_TAG
                    if "source_url" in row:
                        row["source_url"] = (
                            f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_ticker}"
                        )
                    if "retrieved_at" in row:
                        row["retrieved_at"] = retrieved
                    if "data_quality_status" in row:
                        row["data_quality_status"] = "YAHOO_BACKADJUSTED"
                    rewritten += 1
            writer.writerow(row)
    tmp.replace(path)
    return rewritten
