"""Tests for Milestone 3 market-data ingestion and lookup."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func as sa_func
from sqlalchemy import select

from pms_platform.market_data.benchmarks import import_benchmark_tri
from pms_platform.market_data.coverage import (
    build_benchmark_coverage_report,
    build_price_coverage_report,
)
from pms_platform.market_data.dividends import import_dividends
from pms_platform.market_data.identifiers import IdentifierResolver
from pms_platform.market_data.importer import import_market_data
from pms_platform.market_data.lookup import lookup_benchmark_tri, lookup_daily_price
from pms_platform.market_data.prices import import_daily_prices
from pms_platform.market_data.successors import import_security_successors
from pms_platform.market_data.validation import compare_prices_to_snapshots
from pms_platform.models import (
    DailyPrice,
    Dividend,
    ImportBatch,
    InvestmentEpisode,
    PortfolioSnapshotRecord,
    Security,
    SecuritySuccessor,
)

FIXTURE_DIR = Path("tests/fixtures/market_data")


@pytest.fixture
def market_security(session, import_batch) -> Security:
    """Security with current and historical NSE symbols."""
    security = Security(
        security_id="SEC999",
        portfolio_name="TestCo",
        canonical_name="Test Company Limited",
        current_nse_symbol="TESTCO",
        historical_nse_symbol="OLDCO",
        import_batch_id=import_batch.import_batch_id,
    )
    session.add(security)
    session.flush()
    return security


@pytest.fixture
def predecessor_security(session, import_batch) -> Security:
    """Predecessor security for successor-chain tests."""
    security = Security(
        security_id="SEC998",
        portfolio_name="OldCo",
        current_nse_symbol="OLDLEG",
        import_batch_id=import_batch.import_batch_id,
    )
    session.add(security)
    session.flush()
    return security


@pytest.fixture
def closed_episode(session, market_security) -> InvestmentEpisode:
    """Closed episode for coverage tests."""
    episode = InvestmentEpisode(
        security_id=market_security.security_id,
        episode_number=1,
        entry_date=date(2019, 1, 2),
        exit_date=date(2019, 1, 3),
        status="CLOSED",
        initial_quantity=10,
        total_buy_quantity=10,
        total_sell_quantity=10,
        corporate_action_quantity=0,
        max_quantity=10,
        final_quantity=0,
        number_of_buys=1,
        number_of_sells=1,
    )
    session.add(episode)
    session.flush()
    return episode


def _import_fixture_bundle(session) -> None:
    import_security_successors(session, FIXTURE_DIR / "symbol_maps/security_successors.csv")
    import_daily_prices(session, FIXTURE_DIR / "prices/daily_prices.csv")
    import_dividends(session, FIXTURE_DIR / "dividends/dividends.csv")
    import_benchmark_tri(session, FIXTURE_DIR / "benchmarks/benchmark_tri.csv")


def test_import_daily_prices_resolves_symbols_and_skips_duplicates(
    session, market_security, predecessor_security
) -> None:
    result = import_daily_prices(session, FIXTURE_DIR / "prices/daily_prices.csv")

    assert result.inserted == 5
    assert result.unresolved == 1
    assert result.skipped == 1

    prices = session.scalars(select(DailyPrice).order_by(DailyPrice.trade_date)).all()
    assert len(prices) == 5
    resolved_prices = [price for price in prices if price.security_id is not None]
    assert len(resolved_prices) == 4
    assert all(price.security_id == market_security.security_id for price in resolved_prices)
    oldco_price = next(price for price in prices if price.identifier == "OLDCO")
    assert oldco_price.security_id == market_security.security_id


def test_import_daily_prices_is_idempotent(session, market_security, predecessor_security) -> None:
    first = import_daily_prices(session, FIXTURE_DIR / "prices/daily_prices.csv")
    second = import_daily_prices(session, FIXTURE_DIR / "prices/daily_prices.csv")

    assert first.inserted == 5
    assert second.inserted == 0
    assert second.skipped == 5


def test_import_rejects_invalid_price_rows(session, market_security, tmp_path) -> None:
    path = tmp_path / "daily_prices.csv"
    path.write_text(
        "identifier_type,identifier,trade_date,close,adjusted_close,adjustment_basis,volume,currency,source,publication_date\n"
        "NSE_SYMBOL,TESTCO,2019-01-02,0,10,SPLIT_ONLY,,INR,fixture,\n"
        "NSE_SYMBOL,TESTCO,2019-01-03,10,0,SPLIT_ONLY,,INR,fixture,\n"
        "NSE_SYMBOL,TESTCO,2019-01-04,10,10,INVALID,,INR,fixture,\n",
        encoding="utf-8",
    )

    result = import_daily_prices(session, path)

    assert result.inserted == 0
    assert result.invalid == 3


def test_import_dividends_and_benchmarks(session, market_security, predecessor_security) -> None:
    dividend_result = import_dividends(session, FIXTURE_DIR / "dividends/dividends.csv")
    benchmark_result = import_benchmark_tri(session, FIXTURE_DIR / "benchmarks/benchmark_tri.csv")

    assert dividend_result.inserted == 2
    assert dividend_result.unresolved == 1
    assert benchmark_result.inserted == 3
    assert benchmark_result.skipped == 1

    dividend = session.scalar(
        select(Dividend).where(Dividend.security_id == market_security.security_id)
    )
    assert dividend is not None
    assert dividend.security_id == market_security.security_id
    assert dividend.dividend_per_share == Decimal("2.50")


def test_import_benchmark_rejects_invalid_tri_levels(session, tmp_path) -> None:
    path = tmp_path / "benchmark_tri.csv"
    path.write_text(
        "benchmark_code,trade_date,tri_level,source,publication_date,methodology_version\n"
        "BSE_SMALLCAP,2019-01-02,0,fixture,,bse_price_index\n",
        encoding="utf-8",
    )

    result = import_benchmark_tri(session, path)

    assert result.inserted == 0
    assert result.invalid == 1


def test_identifier_resolver_uses_historical_symbol(
    session, market_security, predecessor_security
) -> None:
    import_security_successors(session, FIXTURE_DIR / "symbol_maps/security_successors.csv")
    resolver = IdentifierResolver(session)

    current = resolver.resolve("NSE_SYMBOL", "TESTCO", date(2019, 1, 2))
    historical = resolver.resolve("NSE_SYMBOL", "OLDCO", date(2018, 6, 1))

    assert current.security_id == market_security.security_id
    assert current.status == "RESOLVED"
    assert historical.security_id == market_security.security_id


def test_lookup_uses_prior_trading_day_for_non_trading_dates(
    session, market_security, predecessor_security
) -> None:
    import_daily_prices(session, FIXTURE_DIR / "prices/daily_prices.csv")

    observation = lookup_daily_price(session, market_security.security_id, date(2019, 1, 4))

    assert observation is not None
    assert observation.lookup_mode == "PRIOR_TRADING_DAY"
    assert observation.trade_date == date(2019, 1, 3)
    assert observation.close == Decimal("101.00")
    assert observation.adjusted_close == Decimal("96.00")


def test_benchmark_lookup_exact_and_prior(session) -> None:
    import_benchmark_tri(session, FIXTURE_DIR / "benchmarks/benchmark_tri.csv")

    exact = lookup_benchmark_tri(session, "BSE_SMALLCAP", date(2019, 1, 3))
    prior = lookup_benchmark_tri(session, "BSE_SMALLCAP", date(2019, 1, 4))

    assert exact is not None
    assert exact.lookup_mode == "EXACT"
    assert prior is not None
    assert prior.lookup_mode == "PRIOR_TRADING_DAY"
    assert prior.trade_date == date(2019, 1, 3)


def test_coverage_reports_flag_missing_data(session, closed_episode) -> None:
    price_rows = build_price_coverage_report(session)
    benchmark_rows = build_benchmark_coverage_report(session)

    assert price_rows
    assert all(row.quality_status == "INSUFFICIENT" for row in price_rows)
    assert benchmark_rows
    assert all(row.quality_status == "INSUFFICIENT" for row in benchmark_rows)


def test_coverage_reports_ok_after_import(
    session, market_security, predecessor_security, closed_episode
) -> None:
    _import_fixture_bundle(session)

    price_rows = build_price_coverage_report(session)
    benchmark_rows = build_benchmark_coverage_report(session)

    assert all(row.quality_status == "OK" for row in price_rows)
    assert all(row.quality_status == "OK" for row in benchmark_rows)


def test_compare_prices_to_snapshots_reports_discrepancy(
    session, market_security, import_batch
) -> None:
    import_daily_prices(session, FIXTURE_DIR / "prices/daily_prices.csv")
    session.add(
        PortfolioSnapshotRecord(
            snapshot_date=date(2019, 1, 2),
            security_id=market_security.security_id,
            portfolio_name=market_security.portfolio_name,
            quantity=10,
            market_price=Decimal("120.00"),
            source_file="snapshot.xlsx",
            source_sheet="2019-01-02",
            source_row=2,
            import_batch_id=import_batch.import_batch_id,
        )
    )
    session.flush()

    discrepancies = compare_prices_to_snapshots(session)

    assert len(discrepancies) == 1
    assert discrepancies[0].snapshot_price == Decimal("120.00")
    assert discrepancies[0].market_price == Decimal("100.00")


def test_import_market_data_orchestrator_reports_missing_files(session, tmp_path) -> None:
    result = import_market_data(session, tmp_path)

    assert result.prices is None
    assert result.dividends is None
    assert result.benchmarks is None
    assert result.missing_files == (
        "prices/daily_prices.csv",
        "dividends/dividends.csv",
        "benchmarks/benchmark_tri.csv",
    )


def test_import_market_data_orchestrator_imports_available_files(
    session, market_security, predecessor_security
) -> None:
    result = import_market_data(session, FIXTURE_DIR)

    assert result.prices is not None
    assert result.dividends is not None
    assert result.benchmarks is not None
    assert result.successors is not None
    assert result.missing_files == ()
    count = session.scalar(select(sa_func.count()).select_from(DailyPrice))
    assert count == 5


def test_successor_import_is_idempotent(session, market_security, predecessor_security) -> None:
    path = FIXTURE_DIR / "symbol_maps/security_successors.csv"
    first = import_security_successors(session, path)
    second = import_security_successors(session, path)

    assert first.inserted == 1
    assert second.inserted == 0
    assert second.skipped == 1
    assert session.scalar(select(SecuritySuccessor)) is not None


def test_unconfirmed_successor_portfolio_name_is_insufficient(session, import_batch) -> None:
    session.add(
        Security(
            security_id="SEC777",
            portfolio_name="Geometric",
            current_nse_symbol="GEOMETRIC",
            import_batch_id=import_batch.import_batch_id,
        )
    )
    session.flush()

    resolver = IdentifierResolver(session)
    resolution = resolver.resolve("NSE_SYMBOL", "GEOMETRIC", date(2019, 1, 2))

    assert resolution.security_id == "SEC777"
    assert resolution.status == "INSUFFICIENT"


def test_import_batch_lineage_created(session, market_security, predecessor_security) -> None:
    import_daily_prices(session, FIXTURE_DIR / "prices/daily_prices.csv")

    batch = session.scalar(select(ImportBatch).where(ImportBatch.source_type == "daily_prices"))
    assert batch is not None
    assert batch.source_checksum
