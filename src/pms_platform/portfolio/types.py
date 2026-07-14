"""Portfolio position row."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class PortfolioPosition:
    """Equity holding reconstructed on a specific date."""

    security_id: str
    portfolio_name: str
    quantity: int
    cost_basis: Decimal | None
    market_price: Decimal | None
    market_value: Decimal | None
    portfolio_weight: Decimal | None


@dataclass(frozen=True)
class LiquidPosition:
    """Liquid holding reconstructed on a specific date."""

    quantity: int
    cost_basis: Decimal | None
    market_price: Decimal | None
    market_value: Decimal | None


@dataclass(frozen=True)
class PortfolioSnapshot:
    """In-memory snapshot row parsed from a portfolio workbook."""

    snapshot_date: date
    portfolio_name: str
    quantity: int
    market_price: Decimal | None
    market_value: Decimal | None
    portfolio_weight: Decimal | None
    source_file: str
    source_sheet: str
    source_row: int


@dataclass(frozen=True)
class ReconciliationMismatch:
    """Difference between reconstructed and snapshot quantities."""

    snapshot_date: date
    security_id: str | None
    portfolio_name: str
    reconstructed_quantity: int
    snapshot_quantity: int
    difference: int
    source_file: str
    source_sheet: str
    severity: str
    message: str
