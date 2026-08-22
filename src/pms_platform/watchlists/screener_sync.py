"""Daily Screener-export import + BSE gap-fill for watchlist screener data."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.config import settings
from pms_platform.fundamentals.providers.screener_export import (
    ScreenerExportImportResult,
    find_latest_screener_export,
    import_screener_export,
)
from pms_platform.fundamentals.service import sync_fundamentals
from pms_platform.models.fundamental_snapshot import FundamentalSnapshot
from pms_platform.models.valuation_snapshot import ValuationSnapshot
from pms_platform.watchlists.metrics_cache import rebuild_all_watchlist_metrics
from pms_platform.watchlists.refresh import (
    _all_watchlist_bse_codes,
    _watchlist_bse_codes,
    refresh_watchlist_quotes,
)

# Prefer Screener file dropped here (CSV/XLSX). OneDrive external mount covers Docker.
DEFAULT_SCREENER_SUBDIR = Path("fundamentals") / "screener"


@dataclass(frozen=True)
class ScreenerSyncResult:
    screener: ScreenerExportImportResult | None
    bse_gap_codes: int
    metrics_rows: int
    export_path: str | None


def screener_export_dir(external_dir: Path | None = None) -> Path:
    root = external_dir or settings.external_data_dir
    return Path(root) / DEFAULT_SCREENER_SUBDIR


def codes_needing_bse_gapfill(session: Session, bse_codes: list[str]) -> list[str]:
    """Codes still missing quarterly sales or market cap after Screener import."""
    if not bse_codes:
        return []
    have_sales = set(
        session.scalars(
            select(FundamentalSnapshot.identifier).where(
                FundamentalSnapshot.identifier_type == "BSE_CODE",
                FundamentalSnapshot.identifier.in_(bse_codes),
                FundamentalSnapshot.sales.is_not(None),
            )
        ).all()
    )
    have_mcap = set(
        session.scalars(
            select(ValuationSnapshot.identifier).where(
                ValuationSnapshot.identifier_type == "BSE_CODE",
                ValuationSnapshot.identifier.in_(bse_codes),
                ValuationSnapshot.market_cap_cr.is_not(None),
            )
        ).all()
    )
    return [c for c in bse_codes if c not in have_sales or c not in have_mcap]


def sync_screener_then_bse_gaps(
    session: Session,
    *,
    external_dir: Path | None = None,
    watchlist_id: int | None = None,
    export_path: Path | None = None,
    skip_bse: bool = False,
) -> ScreenerSyncResult:
    """Import latest Screener export, BSE-fill gaps, refresh returns, rebuild metrics.

    Screener.in has no API — drop CSV/XLSX into fundamentals/screener/ before the job.
    """
    export = export_path
    if export is None:
        export = find_latest_screener_export(screener_export_dir(external_dir))

    screener_result: ScreenerExportImportResult | None = None
    if export is not None and export.is_file():
        screener_result = import_screener_export(session, export)
        session.flush()

    if watchlist_id is not None:
        codes = _watchlist_bse_codes(session, watchlist_id)
    else:
        codes = _all_watchlist_bse_codes(session)

    gap_codes = codes_needing_bse_gapfill(session, codes) if not skip_bse else []
    if gap_codes:
        # Quarterly + valuation/promoter/annual path for leftovers only.
        sync_fundamentals(
            session,
            external_dir=external_dir or settings.external_data_dir,
            bse_codes=gap_codes,
            provider="xbrl",
        )
        session.flush()

    # Always refresh price-history returns / 52W from daily_prices for the list.
    refresh_watchlist_quotes(session, watchlist_id=watchlist_id, bse_codes=codes or None)

    if watchlist_id is not None:
        from pms_platform.watchlists.metrics_cache import rebuild_watchlist_metrics

        metrics_rows = rebuild_watchlist_metrics(session, watchlist_id)
    else:
        metrics_rows = rebuild_all_watchlist_metrics(session)

    session.flush()
    return ScreenerSyncResult(
        screener=screener_result,
        bse_gap_codes=len(gap_codes),
        metrics_rows=metrics_rows,
        export_path=str(export) if export else None,
    )
