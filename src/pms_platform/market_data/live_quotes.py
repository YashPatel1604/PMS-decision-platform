"""Refresh open-holding marks from Yahoo Finance into daily_prices."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.market_data.yahoo_finance import (
    SOURCE_NAME,
    LiveQuote,
    YahooFinanceClient,
)
from pms_platform.models import DailyPrice, ImportBatch, InvestmentEpisode, Security
from pms_platform.models.enums import EpisodeStatus

_LIVE_ADJUSTMENT_BASIS = "VENDOR_ADJUSTED"


@dataclass(frozen=True)
class LiveQuoteRefreshResult:
    """Outcome of a live quote refresh."""

    requested: int
    fetched: int
    upserted: int
    missing_symbol: int
    failed: int
    as_of_date: date
    tickers: tuple[str, ...]
    notes: tuple[str, ...]


def bse_ticker_for_security(security: Security) -> str | None:
    """Build a Yahoo/BSE ticker (SYMBOL.BO) from the security master."""
    symbol = (security.current_nse_symbol or security.historical_nse_symbol or "").strip()
    if not symbol:
        return None
    # Yahoo Finance BSE uses NSE-style symbols with .BO, not numeric BSE codes.
    return f"{symbol.upper()}.BO"


def nse_ticker_for_security(security: Security) -> str | None:
    symbol = (security.current_nse_symbol or security.historical_nse_symbol or "").strip()
    if not symbol:
        return None
    return f"{symbol.upper()}.NS"


def historical_bse_ticker_for_security(security: Security) -> str | None:
    """Prior NSE-style symbol on BSE, when different from current."""
    hist = (security.historical_nse_symbol or "").strip().upper()
    current = (security.current_nse_symbol or "").strip().upper()
    if not hist or hist == current:
        return None
    return f"{hist}.BO"


def historical_nse_ticker_for_security(security: Security) -> str | None:
    hist = (security.historical_nse_symbol or "").strip().upper()
    current = (security.current_nse_symbol or "").strip().upper()
    if not hist or hist == current:
        return None
    return f"{hist}.NS"


def _open_securities(
    session: Session,
    security_ids: list[str] | None = None,
) -> list[Security]:
    if security_ids:
        rows = session.scalars(
            select(Security).where(Security.security_id.in_(security_ids))
        ).all()
        return list(rows)

    open_ids = session.scalars(
        select(InvestmentEpisode.security_id).where(
            InvestmentEpisode.status == EpisodeStatus.OPEN.value
        )
    ).all()
    if not open_ids:
        return []
    return list(
        session.scalars(select(Security).where(Security.security_id.in_(list(open_ids)))).all()
    )


def _ensure_live_batch(session: Session, as_of_date: date) -> ImportBatch:
    source_file = f"live://{SOURCE_NAME}/{as_of_date.isoformat()}"
    digest = f"{SOURCE_NAME}:{as_of_date.isoformat()}"
    existing = session.scalar(
        select(ImportBatch).where(
            ImportBatch.source_type == "live_quotes",
            ImportBatch.source_file == source_file,
            ImportBatch.source_checksum == digest,
        )
    )
    if existing is not None:
        return existing
    batch = ImportBatch(
        source_type="live_quotes",
        source_file=source_file,
        source_checksum=digest,
        status="completed",
        notes=f"Live quotes from {SOURCE_NAME}",
    )
    session.add(batch)
    session.flush()
    return batch


def _upsert_quote(
    session: Session,
    *,
    security_id: str,
    quote: LiveQuote,
    batch: ImportBatch,
) -> bool:
    source_key = f"{SOURCE_NAME}|{security_id}|{quote.as_of_date.isoformat()}"
    existing = session.scalar(
        select(DailyPrice).where(
            DailyPrice.security_id == security_id,
            DailyPrice.trade_date == quote.as_of_date,
            DailyPrice.source == SOURCE_NAME,
        )
    )
    if existing is not None:
        existing.close = quote.last_price
        existing.adjusted_close = quote.last_price
        existing.volume = quote.volume
        existing.publication_date = quote.as_of_date
        return False

    # Prefer live row over stale same-day historical if both exist: keep distinct source.
    session.add(
        DailyPrice(
            security_id=security_id,
            identifier_type="SECURITY_ID",
            identifier=security_id,
            trade_date=quote.as_of_date,
            close=quote.last_price,
            adjusted_close=quote.last_price,
            adjustment_basis=_LIVE_ADJUSTMENT_BASIS,
            volume=quote.volume,
            currency="INR",
            source=SOURCE_NAME,
            publication_date=quote.as_of_date,
            source_file=batch.source_file,
            source_row=0,
            source_key=source_key,
            import_batch_id=batch.import_batch_id,
        )
    )
    return True


def refresh_live_quotes(
    session: Session,
    *,
    security_ids: list[str] | None = None,
    prefer_bse: bool = True,
    client: YahooFinanceClient | None = None,
) -> LiveQuoteRefreshResult:
    """Fetch live quotes for open (or selected) securities and upsert daily_prices."""
    api = client or YahooFinanceClient()
    securities = _open_securities(session, security_ids)
    notes: list[str] = []
    ticker_by_security: dict[str, str] = {}
    fallback_tickers: dict[str, list[str]] = {}
    missing_symbol = 0

    for security in securities:
        primary = bse_ticker_for_security(security) if prefer_bse else nse_ticker_for_security(security)
        alt_exchange = nse_ticker_for_security(security) if prefer_bse else bse_ticker_for_security(security)
        hist_primary = (
            historical_bse_ticker_for_security(security)
            if prefer_bse
            else historical_nse_ticker_for_security(security)
        )
        hist_alt = (
            historical_nse_ticker_for_security(security)
            if prefer_bse
            else historical_bse_ticker_for_security(security)
        )
        if primary is None and alt_exchange is None and hist_primary is None:
            missing_symbol += 1
            notes.append(f"{security.security_id}: no NSE symbol for live quote")
            continue
        if primary is not None:
            ticker_by_security[security.security_id] = primary
        elif alt_exchange is not None:
            ticker_by_security[security.security_id] = alt_exchange
        elif hist_primary is not None:
            ticker_by_security[security.security_id] = hist_primary

        fallbacks: list[str] = []
        for candidate in (alt_exchange, hist_primary, hist_alt):
            if (
                candidate
                and candidate != ticker_by_security.get(security.security_id)
                and candidate not in fallbacks
            ):
                fallbacks.append(candidate)
        if fallbacks:
            fallback_tickers[security.security_id] = fallbacks

    primary_tickers = list(dict.fromkeys(ticker_by_security.values()))
    quotes: dict[str, LiveQuote] = {}
    failed = 0
    try:
        quotes = api.fetch_stocks(primary_tickers)
    except Exception as exc:  # noqa: BLE001 - surface as refresh failure note
        notes.append(f"Live API request failed: {exc}")
        return LiveQuoteRefreshResult(
            requested=len(securities),
            fetched=0,
            upserted=0,
            missing_symbol=missing_symbol,
            failed=len(ticker_by_security),
            as_of_date=date.today(),
            tickers=tuple(primary_tickers),
            notes=tuple(notes),
        )

    # Later passes: other exchange and/or historical symbols after rename.
    need_fallback: list[str] = []
    for sid, primary in ticker_by_security.items():
        if quotes.get(primary) is not None:
            continue
        for secondary in fallback_tickers.get(sid, []):
            if secondary not in quotes:
                need_fallback.append(secondary)
    need_fallback = list(dict.fromkeys(need_fallback))
    if need_fallback:
        try:
            quotes.update(api.fetch_stocks(need_fallback))
        except Exception as exc:  # noqa: BLE001
            notes.append(f"Fallback live API request failed: {exc}")

    as_of = date.today()
    if quotes:
        as_of = next(iter(quotes.values())).as_of_date

    batch = _ensure_live_batch(session, as_of)
    upserted = 0
    fetched = 0
    all_tickers = list(dict.fromkeys([*primary_tickers, *need_fallback]))
    for security in securities:
        sid = security.security_id
        primary = ticker_by_security.get(sid)
        quote = quotes.get(primary) if primary else None
        used_ticker = primary if quote is not None else None
        if quote is None:
            for secondary in fallback_tickers.get(sid, []):
                quote = quotes.get(secondary)
                if quote is not None:
                    used_ticker = secondary
                    break
        if quote is None:
            if primary or fallback_tickers.get(sid):
                failed += 1
                tried = " / ".join(
                    t for t in [primary, *fallback_tickers.get(sid, [])] if t
                )
                notes.append(f"{sid}: quote not returned for {tried}")
            continue
        if used_ticker and primary and used_ticker != primary:
            notes.append(f"{sid}: used {used_ticker} (primary {primary} missing)")
        fetched += 1
        inserted = _upsert_quote(session, security_id=sid, quote=quote, batch=batch)
        if inserted:
            upserted += 1
        else:
            upserted += 1  # updated counts as upserted

    session.flush()
    return LiveQuoteRefreshResult(
        requested=len(securities),
        fetched=fetched,
        upserted=upserted,
        missing_symbol=missing_symbol,
        failed=failed,
        as_of_date=as_of,
        tickers=tuple(sorted(set(all_tickers))),
        notes=tuple(notes),
    )
