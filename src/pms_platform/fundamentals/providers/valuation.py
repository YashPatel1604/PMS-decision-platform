"""Valuation snapshot provider — BSE StockTrading + price-return computation."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.market_data.bse_http import bse_headers as _bse_headers
from pms_platform.market_data.bse_stock_quote import (
    BseStockQuote,
    fetch_bse_stock_quote,
)
from pms_platform.market_data.identifiers import IdentifierResolver
from pms_platform.models.valuation_snapshot import ValuationSnapshot

_REQUEST_DELAY_SEC = 0.1
_FETCH_WORKERS = 4
_HUNDRED = Decimal("100")


@dataclass
class ValuationImportResult:
    inserted: int
    updated: int
    skipped: int


def upsert_valuation_snapshot(
    session: Session,
    *,
    identifier_type: str,
    identifier: str,
    security_id: str | None,
    as_of_date: date,
    last_price: Decimal | None = None,
    market_cap_cr: Decimal | None = None,
    pe_ratio: Decimal | None = None,
    industry_pe: Decimal | None = None,
    book_value_per_share: Decimal | None = None,
    price_to_book: Decimal | None = None,
    eps: Decimal | None = None,
    dividend_yield: Decimal | None = None,
    earnings_yield: Decimal | None = None,
    price_to_sales: Decimal | None = None,
    peg_ratio: Decimal | None = None,
    week_52_high: Decimal | None = None,
    week_52_low: Decimal | None = None,
    return_1d_pct: Decimal | None = None,
    return_1m_pct: Decimal | None = None,
    return_3m_pct: Decimal | None = None,
    return_6m_pct: Decimal | None = None,
    return_1y_pct: Decimal | None = None,
    return_3y_pct: Decimal | None = None,
    all_time_high: Decimal | None = None,
    provider: str = "bse_quote",
) -> tuple[ValuationSnapshot, bool]:
    """Insert or update a ValuationSnapshot; returns (row, is_new)."""
    existing = session.scalar(
        select(ValuationSnapshot).where(
            ValuationSnapshot.identifier_type == identifier_type,
            ValuationSnapshot.identifier == identifier,
            ValuationSnapshot.as_of_date == as_of_date,
        )
    )
    fields = dict(
        security_id=security_id,
        last_price=last_price,
        market_cap_cr=market_cap_cr,
        pe_ratio=pe_ratio,
        industry_pe=industry_pe,
        book_value_per_share=book_value_per_share,
        price_to_book=price_to_book,
        eps=eps,
        dividend_yield=dividend_yield,
        earnings_yield=earnings_yield,
        price_to_sales=price_to_sales,
        peg_ratio=peg_ratio,
        week_52_high=week_52_high,
        week_52_low=week_52_low,
        return_1d_pct=return_1d_pct,
        return_1m_pct=return_1m_pct,
        return_3m_pct=return_3m_pct,
        return_6m_pct=return_6m_pct,
        return_1y_pct=return_1y_pct,
        return_3y_pct=return_3y_pct,
        all_time_high=all_time_high,
        provider=provider,
        computed_at=datetime.now(timezone.utc),
    )
    if existing is not None:
        # Don't wipe price-history fields when quote refresh omits them.
        preserve_if_none = {
            "return_1m_pct",
            "return_3m_pct",
            "return_6m_pct",
            "return_1y_pct",
            "return_3y_pct",
            "all_time_high",
            "week_52_high",
            "week_52_low",
        }
        for k, v in fields.items():
            if v is None and k in preserve_if_none:
                continue
            setattr(existing, k, v)
        return existing, False

    row = ValuationSnapshot(
        identifier_type=identifier_type,
        identifier=identifier,
        as_of_date=as_of_date,
        **fields,
    )
    session.add(row)
    return row, True


def _fetch_quotes_parallel(
    bse_codes: list[str],
    *,
    force: bool,
    max_workers: int,
) -> dict[str, BseStockQuote | None]:
    """Fetch quotes with per-worker clients and a bounded thread pool."""

    def _one(code: str) -> tuple[str, BseStockQuote | None]:
        with httpx.Client(headers=_bse_headers(), follow_redirects=True) as client:
            return code, fetch_bse_stock_quote(code, client=client, force=force)

    results: dict[str, BseStockQuote | None] = {}
    workers = min(max_workers, max(1, len(bse_codes)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_one, code) for code in bse_codes]
        for fut in as_completed(futures):
            code, quote = fut.result()
            results[code] = quote
    return results


def refresh_valuation_snapshots(
    session: Session,
    bse_codes: list[str],
    *,
    request_delay_sec: float = _REQUEST_DELAY_SEC,
    force: bool = False,
    max_workers: int = _FETCH_WORKERS,
    trailing_sales_by_code: dict[str, Decimal | None] | None = None,
    pat_3y_cagr_by_code: dict[str, Decimal | None] | None = None,
) -> ValuationImportResult:
    """Fetch BSE StockTrading quotes for each code and upsert ValuationSnapshot rows.

    `trailing_sales_by_code` — TTM sales (₹ Cr) per BSE code, used to derive P/S.
    `pat_3y_cagr_by_code`    — PAT 3-year CAGR pct per BSE code, used to derive PEG.
    Uses the in-process 6h quote cache unless ``force=True``.
    """
    del request_delay_sec  # overlapped by parallel workers
    resolver = IdentifierResolver(session)
    today = date.today()
    inserted = 0
    updated = 0
    skipped = 0

    # Drop hollow rows so a later ensure/refresh will re-fetch.
    hollow = session.scalars(
        select(ValuationSnapshot).where(
            ValuationSnapshot.identifier_type == "BSE_CODE",
            ValuationSnapshot.identifier.in_(bse_codes),
            ValuationSnapshot.market_cap_cr.is_(None),
            ValuationSnapshot.pe_ratio.is_(None),
            ValuationSnapshot.last_price.is_(None),
        )
    ).all()
    for row in hollow:
        session.delete(row)
    if hollow:
        session.flush()

    quotes = _fetch_quotes_parallel(bse_codes, force=force, max_workers=max_workers)

    for bse_code in bse_codes:
        quote = quotes.get(bse_code)
        if quote is None:
            skipped += 1
            continue

        resolution = resolver.resolve("BSE_CODE", bse_code, today)
        security_id = resolution.security_id if resolution.status == "RESOLVED" else None

        earnings_yield: Decimal | None = None
        if quote.pe_ratio and quote.pe_ratio != 0:
            earnings_yield = (_HUNDRED / quote.pe_ratio).quantize(Decimal("0.0001"))

        price_to_sales: Decimal | None = None
        if trailing_sales_by_code:
            ttm_sales = trailing_sales_by_code.get(bse_code)
            if ttm_sales and ttm_sales > 0 and quote.market_cap_cr:
                price_to_sales = (quote.market_cap_cr / ttm_sales).quantize(Decimal("0.0001"))

        peg_ratio: Decimal | None = None
        if pat_3y_cagr_by_code:
            cagr = pat_3y_cagr_by_code.get(bse_code)
            if cagr and cagr > 0 and quote.pe_ratio:
                peg_ratio = (quote.pe_ratio / cagr).quantize(Decimal("0.0001"))

        _, is_new = upsert_valuation_snapshot(
            session,
            identifier_type="BSE_CODE",
            identifier=bse_code,
            security_id=security_id,
            as_of_date=today,
            last_price=quote.last_price,
            market_cap_cr=quote.market_cap_cr,
            pe_ratio=quote.pe_ratio,
            industry_pe=quote.industry_pe,
            book_value_per_share=quote.book_value_per_share,
            price_to_book=quote.price_to_book,
            eps=quote.eps,
            dividend_yield=quote.dividend_yield,
            earnings_yield=earnings_yield,
            price_to_sales=price_to_sales,
            peg_ratio=peg_ratio,
            week_52_high=quote.week_52_high,
            week_52_low=quote.week_52_low,
            return_1d_pct=quote.return_1d_pct,
        )
        if is_new:
            inserted += 1
        else:
            updated += 1

    session.flush()
    return ValuationImportResult(inserted=inserted, updated=updated, skipped=skipped)
