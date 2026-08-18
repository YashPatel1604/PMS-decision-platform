"""Daily quote/shareholding refresh for watchlist codes (no quarterly XBRL)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from pms_platform.fundamentals.providers.promoter import refresh_promoter_snapshots
from pms_platform.fundamentals.providers.valuation import refresh_valuation_snapshots
from pms_platform.fundamentals.service import _valuation_enrichment
from pms_platform.market_data.price_returns import refresh_price_returns
from pms_platform.watchlists.metrics_cache import rebuild_all_watchlist_metrics
from pms_platform.watchlists.refresh import _all_watchlist_bse_codes, _watchlist_bse_codes


@dataclass(frozen=True)
class WatchlistQuotesRefreshResult:
    bse_codes: int
    valuation_updated: int
    promoter_updated: int
    metrics_rows: int


def refresh_watchlist_quotes(
    session: Session,
    *,
    watchlist_id: int | None = None,
) -> WatchlistQuotesRefreshResult:
    """Fetch valuation + promoter + price returns; rebuild materialized screener cache."""
    if watchlist_id is not None:
        codes = _watchlist_bse_codes(session, watchlist_id)
    else:
        codes = _all_watchlist_bse_codes(session)

    val_updated = 0
    prom_updated = 0
    if codes:
        trailing_sales, pat_cagr = _valuation_enrichment(session, codes)
        val = refresh_valuation_snapshots(
            session,
            codes,
            force=False,
            trailing_sales_by_code=trailing_sales,
            pat_3y_cagr_by_code=pat_cagr,
        )
        val_updated = val.inserted + val.updated
        prom = refresh_promoter_snapshots(session, codes)
        prom_updated = prom.inserted + prom.updated
        refresh_price_returns(session, [("BSE_CODE", code) for code in codes])

    if watchlist_id is not None:
        from pms_platform.watchlists.metrics_cache import rebuild_watchlist_metrics

        metrics_rows = rebuild_watchlist_metrics(session, watchlist_id)
    else:
        metrics_rows = rebuild_all_watchlist_metrics(session)

    session.flush()
    return WatchlistQuotesRefreshResult(
        bse_codes=len(codes),
        valuation_updated=val_updated,
        promoter_updated=prom_updated,
        metrics_rows=metrics_rows,
    )
