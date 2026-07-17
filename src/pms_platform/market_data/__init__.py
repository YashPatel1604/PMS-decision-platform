"""Milestone 3 market-data package."""

from pms_platform.market_data.benchmarks import BenchmarkImportResult, import_benchmark_tri
from pms_platform.market_data.contracts import CanonicalPaths
from pms_platform.market_data.coverage import (
    BenchmarkCoverageRow,
    PriceCoverageRow,
    build_benchmark_coverage_report,
    build_price_coverage_report,
    export_benchmark_coverage_report,
    export_price_coverage_report,
)
from pms_platform.market_data.dividends import DividendImportResult, import_dividends
from pms_platform.market_data.importer import MarketDataImportResult, import_market_data
from pms_platform.market_data.lookup import (
    BenchmarkObservation,
    PriceObservation,
    lookup_benchmark_tri,
    lookup_daily_price,
)
from pms_platform.market_data.prices import PriceImportResult, import_daily_prices
from pms_platform.market_data.validation import (
    PriceSnapshotDiscrepancy,
    compare_prices_to_snapshots,
)

__all__ = [
    "BenchmarkCoverageRow",
    "BenchmarkImportResult",
    "BenchmarkObservation",
    "CanonicalPaths",
    "DividendImportResult",
    "MarketDataImportResult",
    "PriceCoverageRow",
    "PriceImportResult",
    "PriceObservation",
    "PriceSnapshotDiscrepancy",
    "build_benchmark_coverage_report",
    "build_price_coverage_report",
    "compare_prices_to_snapshots",
    "export_benchmark_coverage_report",
    "export_price_coverage_report",
    "import_benchmark_tri",
    "import_daily_prices",
    "import_dividends",
    "import_market_data",
    "lookup_benchmark_tri",
    "lookup_daily_price",
]
