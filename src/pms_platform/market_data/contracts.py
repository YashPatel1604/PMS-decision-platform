"""Canonical CSV contracts for Milestone 3 market data."""

from __future__ import annotations

from dataclasses import dataclass

DAILY_PRICES_COLUMNS: tuple[str, ...] = (
    "identifier_type",
    "identifier",
    "trade_date",
    "close",
    "adjusted_close",
    "adjustment_basis",
    "volume",
    "currency",
    "source",
    "publication_date",
)

DIVIDENDS_COLUMNS: tuple[str, ...] = (
    "identifier_type",
    "identifier",
    "ex_date",
    "record_date",
    "payment_date",
    "dividend_per_share",
    "currency",
    "source",
    "publication_date",
)

BENCHMARK_TRI_COLUMNS: tuple[str, ...] = (
    "benchmark_code",
    "trade_date",
    "tri_level",
    "source",
    "publication_date",
    "methodology_version",
)

SECURITY_SUCCESSORS_COLUMNS: tuple[str, ...] = (
    "predecessor_security_id",
    "successor_security_id",
    "effective_date",
    "action_type",
    "confirmed",
)

CORPORATE_ACTIONS_COLUMNS: tuple[str, ...] = (
    "security_id",
    "portfolio_name",
    "action_date",
    "action_type",
    "split_ratio",
    "numerator",
    "denominator",
    "share_multiplier",
    "yahoo_ticker",
    "source",
    "in_transaction_ledger",
    "held_through",
    "pre_qty",
    "quantity_delta",
    "notes",
)

IDENTIFIER_TYPES: frozenset[str] = frozenset(
    {"SECURITY_ID", "NSE_SYMBOL", "BSE_CODE", "ISIN", "PORTFOLIO_NAME"}
)

ADJUSTMENT_BASES: frozenset[str] = frozenset(
    {
        "SPLIT_ONLY",
        "SPLIT_AND_DIVIDEND",
        "TOTAL_RETURN",
        "VENDOR_ADJUSTED",
    }
)

REQUIRED_BENCHMARKS: tuple[str, ...] = ("BSE_SMALLCAP",)

# Securities requiring explicit successor confirmation before price chaining.
UNCONFIRMED_SUCCESSOR_PORTFOLIO_NAMES: frozenset[str] = frozenset({"Geometric", "Llyod Electric"})


@dataclass(frozen=True)
class CanonicalPaths:
    """Expected locations for canonical market-data CSV files."""

    prices: str = "prices/daily_prices.csv"
    dividends: str = "dividends/dividends.csv"
    benchmarks: str = "benchmarks/benchmark_tri.csv"
    successors: str = "symbol_maps/security_successors.csv"
    corporate_actions: str = "corporate_actions/corporate_actions.csv"
    fundamentals: str = "fundamentals/quarterly_fundamentals.csv"
