"""Metric catalog and versioned CSV contract for quarterly fundamentals."""

from __future__ import annotations

from dataclasses import dataclass

CONTRACT_VERSION = "1.0"
COMPUTATION_VERSION = "1.0"
WATCHLIST_METRICS_VERSION = "2.0"
COMPUTATION_VERSION_LEGACY = "1.0"

QUARTERLY_FUNDAMENTALS_COLUMNS: tuple[str, ...] = (
    "contract_version",
    "identifier_type",
    "identifier",
    "fiscal_year",
    "fiscal_quarter",
    "period_end_date",
    "sales",
    "ebitda",
    "ebit",
    "pat",
    "opm",
    "npm",
    "source",
    "provider",
    "retrieved_at",
)

FUNDAMENTALS_PROVIDERS: frozenset[str] = frozenset({"manual", "screener", "yahoo", "xbrl"})


def validated_fundamentals_provider(raw: str | None = None) -> str:
    """Return a supported active provider name (defaults to manual)."""
    from pms_platform.config import settings

    name = (raw or settings.fundamentals_provider).strip().lower()
    if name in FUNDAMENTALS_PROVIDERS:
        return name
    return "manual"


@dataclass(frozen=True)
class MetricDefinition:
    """One screener column definition."""

    key: str
    label: str
    group: str
    format: str
    description: str


METRIC_CATALOG: tuple[MetricDefinition, ...] = (
    MetricDefinition(
        "sales",
        "Sales (Cr)",
        "Base",
        "currency_cr",
        "Quarterly revenue in ₹ crore",
    ),
    MetricDefinition(
        "pat",
        "PAT (Cr)",
        "Base",
        "currency_cr",
        "Profit after tax in ₹ crore",
    ),
    MetricDefinition(
        "opm",
        "OPM %",
        "Base",
        "percent",
        "Operating profit margin",
    ),
    MetricDefinition(
        "npm",
        "NPM %",
        "Base",
        "percent",
        "Net profit margin",
    ),
    MetricDefinition(
        "sales_yoy_pct",
        "Sales YoY %",
        "Growth",
        "percent_signed",
        "Year-over-year sales growth",
    ),
    MetricDefinition(
        "sales_qoq_pct",
        "Sales QoQ %",
        "Growth",
        "percent_signed",
        "Quarter-over-quarter sales growth",
    ),
    MetricDefinition(
        "pat_yoy_pct",
        "PAT YoY %",
        "Growth",
        "percent_signed",
        "Year-over-year PAT growth",
    ),
    MetricDefinition(
        "opm_delta_pp",
        "OPM Δ pp",
        "Margins",
        "pp_signed",
        "OPM change vs same quarter prior year (pp)",
    ),
    MetricDefinition(
        "npm_delta_pp",
        "NPM Δ pp",
        "Margins",
        "pp_signed",
        "NPM change vs same quarter prior year (pp)",
    ),
    # --- Valuation ---
    MetricDefinition(
        "market_cap_cr",
        "Mkt Cap (Cr)",
        "Valuation",
        "currency_cr",
        "Full market capitalisation in ₹ crore",
    ),
    MetricDefinition(
        "pe_ratio",
        "P/E",
        "Valuation",
        "number",
        "Price-to-earnings ratio",
    ),
    MetricDefinition(
        "industry_pe",
        "Industry P/E",
        "Valuation",
        "number",
        "Sector / industry P/E from BSE",
    ),
    MetricDefinition(
        "price_to_book",
        "P/B",
        "Valuation",
        "number",
        "Price-to-book value ratio",
    ),
    MetricDefinition(
        "price_to_sales",
        "P/S",
        "Valuation",
        "number",
        "Price-to-sales ratio (market cap / trailing 12-month sales)",
    ),
    MetricDefinition(
        "eps",
        "EPS (₹)",
        "Valuation",
        "number",
        "Earnings per share",
    ),
    MetricDefinition(
        "book_value_per_share",
        "Book Value (₹)",
        "Valuation",
        "number",
        "Book value per share",
    ),
    MetricDefinition(
        "dividend_yield",
        "Div Yield %",
        "Valuation",
        "percent",
        "Dividend yield",
    ),
    MetricDefinition(
        "earnings_yield",
        "Earnings Yield %",
        "Valuation",
        "percent",
        "Earnings yield (1/PE × 100)",
    ),
    MetricDefinition(
        "peg_ratio",
        "PEG",
        "Valuation",
        "number",
        "Price/earnings-to-growth ratio (PE / PAT 3yr CAGR)",
    ),
    MetricDefinition(
        "week_52_high",
        "52W High (₹)",
        "Valuation",
        "number",
        "52-week high price",
    ),
    MetricDefinition(
        "week_52_low",
        "52W Low (₹)",
        "Valuation",
        "number",
        "52-week low price",
    ),
    # --- Price Returns ---
    MetricDefinition(
        "return_1d_pct",
        "1D Return %",
        "Price Returns",
        "percent_signed",
        "1-day price return",
    ),
    MetricDefinition(
        "return_1m_pct",
        "1M Return %",
        "Price Returns",
        "percent_signed",
        "1-month price return",
    ),
    MetricDefinition(
        "return_3m_pct",
        "3M Return %",
        "Price Returns",
        "percent_signed",
        "3-month price return",
    ),
    MetricDefinition(
        "return_6m_pct",
        "6M Return %",
        "Price Returns",
        "percent_signed",
        "6-month price return",
    ),
    MetricDefinition(
        "return_1y_pct",
        "1Y Return %",
        "Price Returns",
        "percent_signed",
        "1-year price return",
    ),
    MetricDefinition(
        "return_3y_pct",
        "3Y Return %",
        "Price Returns",
        "percent_signed",
        "3-year price return",
    ),
    MetricDefinition(
        "all_time_high",
        "All-time High (₹)",
        "Price Returns",
        "number",
        "All-time high closing price",
    ),
    # --- Promoter / Governance ---
    MetricDefinition(
        "promoter_holding_pct",
        "Promoter Hold %",
        "Governance",
        "percent",
        "Promoter shareholding percentage (latest quarter)",
    ),
    MetricDefinition(
        "promoter_holding_change_pp",
        "Promoter Chg pp",
        "Governance",
        "pp_signed",
        "Change in promoter holding vs prior quarter (pp)",
    ),
    MetricDefinition(
        "pledged_pct",
        "Pledged %",
        "Governance",
        "percent",
        "Percentage of promoter shares pledged",
    ),
    # --- Quality / Balance Sheet ---
    MetricDefinition(
        "roce",
        "ROCE %",
        "Quality",
        "percent",
        "Return on capital employed",
    ),
    MetricDefinition(
        "roe",
        "ROE %",
        "Quality",
        "percent",
        "Return on equity",
    ),
    MetricDefinition(
        "roa",
        "ROA %",
        "Quality",
        "percent",
        "Return on assets",
    ),
    MetricDefinition(
        "debt_to_equity",
        "D/E",
        "Quality",
        "number",
        "Debt-to-equity ratio",
    ),
    MetricDefinition(
        "interest_coverage",
        "Int. Coverage",
        "Quality",
        "number",
        "Interest coverage ratio (EBIT / Finance cost)",
    ),
    MetricDefinition(
        "current_ratio",
        "Current Ratio",
        "Quality",
        "number",
        "Current assets / current liabilities",
    ),
    # --- Multi-year Growth ---
    MetricDefinition(
        "sales_3y_cagr",
        "Sales 3Y CAGR %",
        "Historical Growth",
        "percent_signed",
        "Sales compound annual growth rate over 3 years",
    ),
    MetricDefinition(
        "sales_5y_cagr",
        "Sales 5Y CAGR %",
        "Historical Growth",
        "percent_signed",
        "Sales compound annual growth rate over 5 years",
    ),
    MetricDefinition(
        "pat_3y_cagr",
        "PAT 3Y CAGR %",
        "Historical Growth",
        "percent_signed",
        "PAT compound annual growth rate over 3 years",
    ),
    MetricDefinition(
        "pat_5y_cagr",
        "PAT 5Y CAGR %",
        "Historical Growth",
        "percent_signed",
        "PAT compound annual growth rate over 5 years",
    ),
)
