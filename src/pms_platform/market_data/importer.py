"""Market-data import orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from pms_platform.market_data.benchmarks import BenchmarkImportResult, import_benchmark_tri
from pms_platform.market_data.contracts import CanonicalPaths
from pms_platform.market_data.dividends import DividendImportResult, import_dividends
from pms_platform.market_data.prices import PriceImportResult, import_daily_prices
from pms_platform.market_data.successors import SuccessorImportResult, import_security_successors


@dataclass(frozen=True)
class MarketDataImportResult:
    """Combined outcome of all Milestone 3 imports."""

    prices: PriceImportResult | None
    dividends: DividendImportResult | None
    benchmarks: BenchmarkImportResult | None
    successors: SuccessorImportResult | None
    missing_files: tuple[str, ...]


def import_market_data(session: Session, external_dir: Path) -> MarketDataImportResult:
    """Import all available canonical market-data files from external_dir."""
    paths = CanonicalPaths()
    missing: list[str] = []

    prices_path = external_dir / paths.prices
    dividends_path = external_dir / paths.dividends
    benchmarks_path = external_dir / paths.benchmarks
    successors_path = external_dir / paths.successors

    successors_result: SuccessorImportResult | None = None
    if successors_path.exists():
        successors_result = import_security_successors(session, successors_path)

    prices_result: PriceImportResult | None = None
    if prices_path.exists():
        prices_result = import_daily_prices(session, prices_path)
    else:
        missing.append(paths.prices)

    dividends_result: DividendImportResult | None = None
    if dividends_path.exists():
        dividends_result = import_dividends(session, dividends_path)
    else:
        missing.append(paths.dividends)

    benchmarks_result: BenchmarkImportResult | None = None
    if benchmarks_path.exists():
        benchmarks_result = import_benchmark_tri(session, benchmarks_path)
    else:
        missing.append(paths.benchmarks)

    return MarketDataImportResult(
        prices=prices_result,
        dividends=dividends_result,
        benchmarks=benchmarks_result,
        successors=successors_result,
        missing_files=tuple(missing),
    )
