"""Fundamentals sync orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.config import settings
from pms_platform.fundamentals.catalog import COMPUTATION_VERSION, validated_fundamentals_provider
from pms_platform.fundamentals.compute import compute_snapshots_for_identifier, upsert_snapshot
from pms_platform.fundamentals.import_csv import FundamentalsImportResult, import_quarterly_fundamentals
from pms_platform.fundamentals.providers.base import FundamentalsProvider, ProviderImportResult
from pms_platform.fundamentals.providers.manual_csv import ManualCsvProvider, ScreenerExportProvider
from pms_platform.fundamentals.providers.promoter import refresh_promoter_snapshots
from pms_platform.fundamentals.providers.valuation import refresh_valuation_snapshots
from pms_platform.fundamentals.providers.yahoo import YahooFundamentalsProvider
from pms_platform.fundamentals.providers.xbrl import XbrlFundamentalsProvider
from pms_platform.models.company_fundamentals_quarterly import CompanyFundamentalsQuarterly


@dataclass(frozen=True)
class FundamentalsSyncResult:
    """Combined import + snapshot recompute outcome."""

    import_result: FundamentalsImportResult | None
    yahoo_result: ProviderImportResult | None
    bse_result: ProviderImportResult | None
    snapshots_written: int
    identifiers_processed: int


def get_provider(name: str | None = None) -> FundamentalsProvider:
    """Return the configured fundamentals provider."""
    provider_name = validated_fundamentals_provider(name)
    if provider_name == "screener":
        return ScreenerExportProvider()
    if provider_name == "yahoo":
        return YahooFundamentalsProvider()
    if provider_name == "xbrl":
        return XbrlFundamentalsProvider()
    return ManualCsvProvider()


def import_fundamentals_csv(
    session: Session,
    path: Path,
    *,
    provider: str | None = None,
) -> FundamentalsImportResult:
    """Import quarterly fundamentals CSV and recompute snapshots."""
    provider_name = (provider or settings.fundamentals_provider).strip().lower()
    result = import_quarterly_fundamentals(session, path, provider=provider_name)
    recompute_all_snapshots(session)
    return result


def recompute_all_snapshots(
    session: Session,
    *,
    computation_version: str = COMPUTATION_VERSION,
) -> int:
    """Recompute snapshots for every identifier with quarterly data."""
    rows = session.scalars(select(CompanyFundamentalsQuarterly)).all()
    return _recompute_grouped(session, rows, computation_version=computation_version)


def recompute_snapshots_for_identifiers(
    session: Session,
    identifiers: list[tuple[str, str]],
    *,
    computation_version: str = COMPUTATION_VERSION,
) -> int:
    """Recompute snapshots only for the given (identifier_type, identifier) pairs."""
    if not identifiers:
        return 0
    keys = set(identifiers)
    rows = session.scalars(select(CompanyFundamentalsQuarterly)).all()
    filtered = [row for row in rows if (row.identifier_type, row.identifier) in keys]
    return _recompute_grouped(session, filtered, computation_version=computation_version)


def _recompute_grouped(
    session: Session,
    rows: list[CompanyFundamentalsQuarterly],
    *,
    computation_version: str,
) -> int:
    grouped: dict[tuple[str, str], list[CompanyFundamentalsQuarterly]] = {}
    for row in rows:
        key = (row.identifier_type, row.identifier)
        grouped.setdefault(key, []).append(row)

    written = 0
    for group in grouped.values():
        for computed in compute_snapshots_for_identifier(group):
            upsert_snapshot(session, computed, computation_version=computation_version)
            written += 1
    session.flush()
    return written


def sync_fundamentals(
    session: Session,
    *,
    external_dir: Path | None = None,
    provider: str | None = None,
    include_yahoo_fallback: bool = False,
    bse_codes: list[str] | None = None,
    bse_all_securities: bool = False,
    include_valuation: bool = True,
) -> FundamentalsSyncResult:
    """Import fundamentals from CSV, BSE, and/or Yahoo, then recompute snapshots.

    When ``include_valuation`` and scoped ``bse_codes`` are provided, also refresh
    valuation + promoter snapshots for those codes (annual stays lazy on screener).
    """
    data_dir = external_dir or settings.external_data_dir
    csv_path = data_dir / "fundamentals" / "quarterly_fundamentals.csv"
    provider_name = (provider or settings.fundamentals_provider).strip().lower()

    touched: set[tuple[str, str]] = set()

    import_result: FundamentalsImportResult | None = None
    if provider_name in {"manual", "screener"} and csv_path.exists():
        import_result = import_quarterly_fundamentals(
            session,
            csv_path,
            provider=provider_name,
        )

    bse_result: ProviderImportResult | None = None
    if provider_name == "xbrl":
        bse_result = XbrlFundamentalsProvider().import_data(
            session,
            bse_codes=bse_codes,
            include_all_securities=bse_all_securities,
        )
        if bse_codes:
            for code in bse_codes:
                if code and str(code).strip():
                    touched.add(("BSE_CODE", str(code).strip()))

    yahoo_result: ProviderImportResult | None = None
    if include_yahoo_fallback or provider_name == "yahoo":
        yahoo_result = YahooFundamentalsProvider().import_data(session)

    if include_valuation and bse_codes:
        codes = sorted({str(c).strip() for c in bse_codes if c and str(c).strip()})
        if codes:
            try:
                refresh_valuation_snapshots(session, codes, force=False)
            except Exception:
                pass
            try:
                refresh_promoter_snapshots(session, codes)
            except Exception:
                pass
            for code in codes:
                touched.add(("BSE_CODE", code))

    if touched and not (import_result or yahoo_result or bse_all_securities):
        snapshots_written = recompute_snapshots_for_identifiers(session, list(touched))
        identifiers_processed = len(touched)
    else:
        snapshots_written = recompute_all_snapshots(session)
        identifiers_processed = len(
            {
                (row.identifier_type, row.identifier)
                for row in session.scalars(select(CompanyFundamentalsQuarterly)).all()
            }
        )

    return FundamentalsSyncResult(
        import_result=import_result,
        yahoo_result=yahoo_result,
        bse_result=bse_result,
        snapshots_written=snapshots_written,
        identifiers_processed=identifiers_processed,
    )
