"""CLI entry point for the PMS decision platform."""

from __future__ import annotations

import argparse
import getpass
import sys
from datetime import date, timedelta
from pathlib import Path

from alembic import command
from alembic.config import Config

from pms_platform.analytics.exports import (
    export_episode_cash_flows_csv,
    export_episode_performance_csv,
    export_first_buy_price_audit_csv,
    export_post_exit_performance_csv,
    export_sell_assessments_csv,
    export_sell_since_workbook,
)
from pms_platform.analytics.service import run_full_episode_analysis
from pms_platform.auth.service import create_user
from pms_platform.config import settings
from pms_platform.db.base import get_session_factory
from pms_platform.fundamentals.service import sync_fundamentals
from pms_platform.watchlists.quotes_refresh import refresh_watchlist_quotes
from pms_platform.watchlists.refresh import refresh_watchlist_fundamentals, sync_all_watchlists
from pms_platform.episodes.builder import build_episodes
from pms_platform.ingestion.exports import (
    export_decision_events_csv,
    export_episodes_csv,
    export_portfolio_csv,
    export_reconciliation_report_csv,
    export_validation_report_csv,
)
from pms_platform.ingestion.securities import import_security_master
from pms_platform.ingestion.snapshots import import_portfolio_snapshots
from pms_platform.ingestion.transactions import import_transaction_master
from pms_platform.ingestion.validators import ValidationSeverity, validate_imported_data
from pms_platform.market_data.coverage import (
    build_benchmark_coverage_report,
    build_price_coverage_report,
    export_benchmark_coverage_report,
    export_price_coverage_report,
    summarize_benchmark_inventory,
    summarize_price_inventory,
)
from pms_platform.market_data.importer import import_market_data
from pms_platform.market_data.live_quotes import refresh_live_quotes
from pms_platform.market_data.validation import compare_prices_to_snapshots
from pms_platform.portfolio.cash_engine import liquid_on
from pms_platform.portfolio.position_engine import portfolio_on
from pms_platform.portfolio.reconciliation import reconcile_all_snapshots


def _ensure_schema() -> None:
    """Apply Alembic migrations before running commands."""
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(alembic_cfg, "head")


def _parse_date(value: str) -> date:
    """Parse an ISO date string."""
    return date.fromisoformat(value)


def import_all(export_dir: Path | None = None) -> int:
    """Import master files, build episodes, and export CSV outputs."""
    output_dir = export_dir or settings.export_dir
    security_path = settings.raw_data_dir / "security_master" / "SECURITY_MASTER_V1.xlsx"
    transaction_path = settings.raw_data_dir / "transactions" / "MASTER_TRANSACTIONS_V1.xlsx"

    if not security_path.exists():
        print(f"Missing security master: {security_path}", file=sys.stderr)
        return 1
    if not transaction_path.exists():
        print(f"Missing transaction master: {transaction_path}", file=sys.stderr)
        return 1

    _ensure_schema()
    session = get_session_factory()()
    try:
        security_result = import_security_master(session, security_path)
        transaction_result = import_transaction_master(session, transaction_path)
        issues = validate_imported_data(session)

        errors = [issue for issue in issues if issue.severity == ValidationSeverity.ERROR]
        if errors:
            export_validation_report_csv(issues, output_dir / "validation_report.csv")
            session.commit()
            print(f"Validation failed with {len(errors)} error(s). See validation_report.csv")
            return 1

        episodes, decision_events = build_episodes(session)
        session.commit()

        export_episodes_csv(session, output_dir / "investment_episodes.csv")
        export_decision_events_csv(session, output_dir / "decision_events.csv")
        export_validation_report_csv(issues, output_dir / "validation_report.csv")

        print("Import complete.")
        print(
            f"  Securities: inserted={security_result.inserted}, updated={security_result.updated}, "
            f"skipped={security_result.skipped}"
        )
        print(
            f"  Equity txns: inserted={transaction_result.equity_inserted}, "
            f"skipped={transaction_result.equity_skipped}"
        )
        print(
            f"  Liquid txns: inserted={transaction_result.liquid_inserted}, "
            f"skipped={transaction_result.liquid_skipped}"
        )
        print(f"  Summary rows skipped: {transaction_result.summary_rows_skipped}")
        print(f"  Episodes: {len(episodes)}")
        print(f"  Decision events: {len(decision_events)}")
        print(f"  Validation warnings: {len(issues)}")
        print(f"  Exports written to: {output_dir.resolve()}")
        return 0
    except Exception as exc:
        session.rollback()
        print(f"Import failed: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()


def import_snapshots(snapshot_dir: Path | None = None) -> int:
    """Import historical portfolio snapshot workbooks."""
    from pms_platform.research_paths import default_portfolio_snapshots_dir

    _ensure_schema()
    session = get_session_factory()()
    try:
        result = import_portfolio_snapshots(
            session, snapshot_dir or default_portfolio_snapshots_dir()
        )
        session.commit()
        print("Snapshot import complete.")
        print(f"  Inserted: {result.inserted}")
        print(f"  Skipped: {result.skipped}")
        print(f"  Unresolved names: {result.unresolved_names}")
        return 0
    except Exception as exc:
        session.rollback()
        print(f"Snapshot import failed: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()


def portfolio_on_date(as_of_date: date, export_dir: Path | None = None) -> int:
    """Reconstruct and export the portfolio on a specific date."""
    output_dir = export_dir or settings.export_dir
    _ensure_schema()
    session = get_session_factory()()
    try:
        positions = portfolio_on(session, as_of_date)
        liquid = liquid_on(session, as_of_date)
        export_portfolio_csv(
            positions, liquid, output_dir / f"portfolio_{as_of_date.isoformat()}.csv"
        )

        print(f"Portfolio reconstructed for {as_of_date.isoformat()}.")
        print(f"  Equity holdings: {len(positions)}")
        print(f"  Liquid quantity: {liquid.quantity if liquid else 0}")
        print(f"  Export: {(output_dir / f'portfolio_{as_of_date.isoformat()}.csv').resolve()}")
        return 0
    except Exception as exc:
        print(f"Portfolio reconstruction failed: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()


def reconcile_snapshots(snapshot_dir: Path | None = None, export_dir: Path | None = None) -> int:
    """Reconcile reconstructed quantities against all snapshot workbooks."""
    output_dir = export_dir or settings.export_dir
    _ensure_schema()
    session = get_session_factory()()
    try:
        mismatches = reconcile_all_snapshots(
            session,
            snapshot_dir or settings.raw_data_dir / "portfolio_snapshots",
        )
        export_reconciliation_report_csv(mismatches, output_dir / "reconciliation_report.csv")

        errors = [mismatch for mismatch in mismatches if mismatch.severity == "ERROR"]
        warnings = [mismatch for mismatch in mismatches if mismatch.severity == "WARNING"]
        print("Snapshot reconciliation complete.")
        print(f"  Errors: {len(errors)}")
        print(f"  Warnings: {len(warnings)}")
        print(f"  Report: {(output_dir / 'reconciliation_report.csv').resolve()}")
        return 0
    except Exception as exc:
        print(f"Snapshot reconciliation failed: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()


def import_fundamentals_cmd(
    external_dir: Path | None = None,
    *,
    provider: str | None = None,
    yahoo_fallback: bool = False,
    bse_all_securities: bool = False,
) -> int:
    """Import quarterly fundamentals CSV and recompute snapshots."""
    data_dir = external_dir or settings.external_data_dir
    _ensure_schema()
    session = get_session_factory()()
    try:
        result = sync_fundamentals(
            session,
            external_dir=data_dir,
            provider=provider,
            include_yahoo_fallback=yahoo_fallback,
            bse_all_securities=bse_all_securities,
        )
        session.commit()

        print("Fundamentals import complete.")
        print(f"  Provider: {provider or settings.fundamentals_provider}")
        if result.import_result is not None:
            imp = result.import_result
            print(
                f"  CSV: inserted={imp.inserted}, updated={imp.updated}, "
                f"skipped={imp.skipped}, invalid={imp.invalid}"
            )
        if result.yahoo_result is not None:
            yahoo = result.yahoo_result
            print(
                f"  Yahoo: inserted={yahoo.inserted}, updated={yahoo.updated}, "
                f"invalid={yahoo.invalid}"
            )
        if result.bse_result is not None:
            bse = result.bse_result
            print(
                f"  BSE: inserted={bse.inserted}, updated={bse.updated}, "
                f"skipped={bse.skipped}, invalid={bse.invalid}"
            )
        print(
            f"  Snapshots: {result.snapshots_written} rows, "
            f"{result.identifiers_processed} identifiers"
        )
        return 0
    except Exception as exc:
        session.rollback()
        print(f"Fundamentals import failed: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()


def refresh_watchlist_quotes_cmd(
    *,
    watchlist_id: int | None = None,
) -> int:
    """Daily job: valuation + promoter + price returns + materialized screener cache."""
    _ensure_schema()
    session = get_session_factory()()
    try:
        result = refresh_watchlist_quotes(session, watchlist_id=watchlist_id)
        session.commit()
        print("Watchlist quotes refresh complete.")
        print(f"  BSE codes: {result.bse_codes}")
        print(f"  Valuation rows touched: {result.valuation_updated}")
        print(f"  Promoter rows touched: {result.promoter_updated}")
        print(f"  Materialized screener rows: {result.metrics_rows}")
        return 0
    except Exception as exc:
        session.rollback()
        print(f"Watchlist quotes refresh failed: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()


def refresh_watchlist_fundamentals_cmd(
    external_dir: Path | None = None,
    *,
    watchlist_id: int | None = None,
) -> int:
    """Fetch BSE data for watchlist codes, persist, and recompute snapshots only."""
    _ensure_schema()
    session = get_session_factory()()
    try:
        result = refresh_watchlist_fundamentals(
            session,
            external_dir=external_dir,
            watchlist_id=watchlist_id,
        )
        session.commit()

        print("Watchlist fundamentals refresh complete.")
        print(f"  Provider: {settings.fundamentals_provider}")
        if result.bse_result is not None:
            bse = result.bse_result
            print(
                f"  BSE quarterly: inserted={bse.inserted}, updated={bse.updated}, "
                f"skipped={bse.skipped}, invalid={bse.invalid}"
            )
        print(
            f"  Snapshots: {result.snapshots_written} rows, "
            f"{result.identifiers_processed} identifiers"
        )
        return 0
    except Exception as exc:
        session.rollback()
        print(f"Watchlist fundamentals refresh failed: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()


def sync_watchlists_cmd(
    external_dir: Path | None = None,
    *,
    watchlist_id: int | None = None,
    skip_fundamentals: bool = False,
) -> int:
    """Resolve symbols, import fundamentals, and poll alerts for watchlists."""
    _ensure_schema()
    session = get_session_factory()()
    try:
        result = sync_all_watchlists(
            session,
            external_dir=external_dir,
            include_fundamentals=not skip_fundamentals,
            watchlist_id=watchlist_id,
        )
        session.commit()

        print("Watchlist sync complete.")
        print(f"  Provider: {settings.fundamentals_provider}")
        if result.fundamentals is not None:
            f = result.fundamentals
            print(
                f"  Fundamentals: inserted={f.csv_inserted}, updated={f.csv_updated}, "
                f"skipped={f.csv_skipped}, invalid={f.csv_invalid}, "
                f"snapshots={f.snapshots_written}, identifiers={f.identifiers_processed}"
            )
        for row in result.results:
            print(
                f"  {row.watchlist_name}: resolved={row.resolution.resolved}, "
                f"failed={row.resolution.failed}, alerts+={row.alerts.inserted} "
                f"({row.duration_ms}ms)"
            )
        return 0
    except Exception as exc:
        session.rollback()
        print(f"Watchlist sync failed: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()


def import_market_data_cmd(external_dir: Path | None = None) -> int:
    """Import canonical market-data CSV files from the external data directory."""
    data_dir = external_dir or settings.external_data_dir
    _ensure_schema()
    session = get_session_factory()()
    try:
        result = import_market_data(session, data_dir)
        session.commit()

        print("Market-data import complete.")
        if result.successors is not None:
            print(
                f"  Successors: inserted={result.successors.inserted}, "
                f"skipped={result.successors.skipped}, invalid={result.successors.invalid}"
            )
        if result.prices is not None:
            print(
                f"  Prices: inserted={result.prices.inserted}, skipped={result.prices.skipped}, "
                f"unresolved={result.prices.unresolved}, invalid={result.prices.invalid}"
            )
        if result.dividends is not None:
            print(
                f"  Dividends: inserted={result.dividends.inserted}, "
                f"skipped={result.dividends.skipped}, unresolved={result.dividends.unresolved}, "
                f"invalid={result.dividends.invalid}"
            )
        if result.benchmarks is not None:
            print(
                f"  Benchmarks: inserted={result.benchmarks.inserted}, "
                f"skipped={result.benchmarks.skipped}, invalid={result.benchmarks.invalid}"
            )
        if result.missing_files:
            print("  Missing files:")
            for missing in result.missing_files:
                print(f"    - {missing}")
        return 0
    except Exception as exc:
        session.rollback()
        print(f"Market-data import failed: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()


def market_data_coverage(export_dir: Path | None = None) -> int:
    """Export price and benchmark coverage reports."""
    output_dir = export_dir or settings.export_dir
    _ensure_schema()
    session = get_session_factory()()
    try:
        price_rows = build_price_coverage_report(session)
        benchmark_rows = build_benchmark_coverage_report(session)
        export_price_coverage_report(price_rows, output_dir / "price_coverage_report.csv")
        export_benchmark_coverage_report(
            benchmark_rows, output_dir / "benchmark_coverage_report.csv"
        )

        price_insufficient = sum(1 for row in price_rows if row.quality_status == "INSUFFICIENT")
        benchmark_insufficient = sum(
            1 for row in benchmark_rows if row.quality_status == "INSUFFICIENT"
        )
        snapshot_discrepancies = compare_prices_to_snapshots(session)

        print("Market-data coverage report complete.")
        print(f"  Price requirements: {len(price_rows)} ({price_insufficient} insufficient)")
        print(
            f"  Benchmark requirements: {len(benchmark_rows)} "
            f"({benchmark_insufficient} insufficient)"
        )
        print(f"  Price inventory securities: {len(summarize_price_inventory(session))}")
        print(f"  Benchmark inventory series: {len(summarize_benchmark_inventory(session))}")
        print(f"  Snapshot price discrepancies: {len(snapshot_discrepancies)}")
        print(f"  Price report: {(output_dir / 'price_coverage_report.csv').resolve()}")
        print(f"  Benchmark report: {(output_dir / 'benchmark_coverage_report.csv').resolve()}")
        return 0
    except Exception as exc:
        print(f"Market-data coverage failed: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()


def refresh_live_quotes_cmd(*, prefer_bse: bool = True) -> int:
    """Fetch live BSE/NSE quotes for open holdings via Indian Stock Market API."""
    _ensure_schema()
    session = get_session_factory()()
    try:
        result = refresh_live_quotes(session, prefer_bse=prefer_bse)
        session.commit()
        exchange = "BSE (.BO)" if prefer_bse else "NSE (.NS)"
        print(f"Live quote refresh complete ({exchange}).")
        print(f"  Requested: {result.requested}")
        print(f"  Fetched: {result.fetched}")
        print(f"  Upserted: {result.upserted}")
        print(f"  Missing symbol: {result.missing_symbol}")
        print(f"  Failed: {result.failed}")
        print(f"  As-of: {result.as_of_date.isoformat()}")
        if result.notes:
            print("  Notes:")
            for note in result.notes[:20]:
                print(f"    - {note}")
        return 0 if result.failed == 0 or result.fetched > 0 else 1
    except Exception as exc:
        session.rollback()
        print(f"Live quote refresh failed: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()


def repair_prices_yahoo_cmd(
    *,
    security_id: str | None,
    portfolio_name: str | None,
    seed_csv: Path | None,
) -> int:
    """Overwrite one security's daily prices with Yahoo back-adjusted history."""
    from pms_platform.market_data.repair_prices import repair_security_prices_from_yahoo

    _ensure_schema()
    session = get_session_factory()()
    seed = seed_csv or Path("docker/market_data_seed/prices/daily_prices.csv")
    try:
        result = repair_security_prices_from_yahoo(
            session,
            security_id=security_id,
            portfolio_name=portfolio_name,
            seed_csv=seed if seed.exists() else None,
        )
        session.commit()
        print(f"Repaired {result.portfolio_name} ({result.security_id}) from {result.yahoo_ticker}")
        print(f"  Bars fetched: {result.bars_fetched}")
        print(f"  Rows updated: {result.rows_updated}")
        print(f"  Rows inserted: {result.rows_inserted}")
        print(f"  Seed CSV rows rewritten: {result.csv_rows_rewritten}")
        return 0
    except Exception as exc:
        session.rollback()
        print(f"Price repair failed: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()


def build_corporate_actions_cmd(
    *,
    output: Path | None = None,
    security_master: Path | None = None,
    transactions: Path | None = None,
) -> int:
    """Fetch Yahoo splits/bonuses and write the canonical corporate-actions CSV."""
    from pms_platform.market_data.corporate_actions import (
        build_corporate_actions_from_yahoo,
        clear_corporate_actions_cache,
        write_corporate_actions_csv,
    )
    from pms_platform.masters.paths import MasterKind, resolve_master_path

    sec_path = security_master or resolve_master_path(MasterKind.SECURITY)
    txn_path = transactions or resolve_master_path(MasterKind.TRANSACTIONS)
    if sec_path is None or not sec_path.exists():
        print("Missing security master", file=sys.stderr)
        return 1
    if txn_path is None or not txn_path.exists():
        print("Missing transactions master", file=sys.stderr)
        return 1

    seed_out = Path("docker/market_data_seed/corporate_actions/corporate_actions.csv")
    export_out = (output or settings.export_dir / "corporate_actions.csv").resolve()
    external_out = Path(settings.external_data_dir) / "corporate_actions" / "corporate_actions.csv"

    print(f"Building corporate-action calendar from Yahoo…")
    print(f"  Security master: {sec_path}")
    print(f"  Transactions:    {txn_path}")
    rows = build_corporate_actions_from_yahoo(
        security_master_path=sec_path,
        transactions_path=txn_path,
    )
    for path in (seed_out, export_out, external_out):
        write_corporate_actions_csv(path, rows)
    clear_corporate_actions_cache()

    held_gaps = [r for r in rows if r.held_through and not r.in_transaction_ledger]
    ledger_matched = sum(1 for r in rows if r.in_transaction_ledger)
    print(f"Corporate actions written: {len(rows)}")
    print(f"  Matched transaction ledger: {ledger_matched}")
    print(f"  Held-through but missing ledger qty event: {len(held_gaps)}")
    for gap in held_gaps:
        print(
            f"    - {gap.action_date} {gap.portfolio_name} {gap.split_ratio} "
            f"pre={gap.pre_qty} delta={gap.quantity_delta}"
        )
    print(f"  Seed (Dad Docker): {seed_out.resolve()}")
    print(f"  Export:            {export_out}")
    print(f"  External:          {external_out.resolve()}")
    return 0


def analyze_episodes(export_dir: Path | None = None) -> int:
    """Compute closed-episode performance metrics and export CSV outputs."""
    output_dir = export_dir or settings.export_dir
    _ensure_schema()
    session = get_session_factory()()
    try:
        summary = run_full_episode_analysis(session)
        export_episode_performance_csv(session, output_dir / "episode_performance.csv")
        export_episode_cash_flows_csv(session, output_dir / "episode_cash_flows.csv")
        export_post_exit_performance_csv(session, output_dir / "post_exit_performance.csv")
        export_sell_assessments_csv(session, output_dir / "sell_assessments.csv")
        export_first_buy_price_audit_csv(
            session,
            output_dir / "first_buy_price_audit.csv",
        )
        export_sell_since_workbook(session, output_dir / "sell_since_analysis.xlsx")
        session.commit()
        print("Episode analysis complete.")
        print(f"  Ownership OK: {summary.ownership_ok}")
        print(f"  Ownership insufficient: {summary.ownership_insufficient}")
        print(f"  Post-exit OK: {summary.post_exit_ok}")
        print(f"  Post-exit insufficient: {summary.post_exit_insufficient}")
        print(f"  Cash-flow rows: {summary.cash_flow_rows}")
        print(f"  Performance report: {(output_dir / 'episode_performance.csv').resolve()}")
        print(f"  Post-exit report: {(output_dir / 'post_exit_performance.csv').resolve()}")
        print(f"  Sell assessments: {(output_dir / 'sell_assessments.csv').resolve()}")
        print(
            "  First-buy audit: "
            f"{(output_dir / 'first_buy_price_audit.csv').resolve()}"
        )
        print(f"  Excel workbook: {(output_dir / 'sell_since_analysis.xlsx').resolve()}")
        return 0
    except Exception as exc:
        session.rollback()
        print(f"Episode analysis failed: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()


def create_user_cmd(
    email: str,
    display_name: str,
    role: str = "member",
    password: str | None = None,
) -> int:
    """Create an invite-only application user."""
    pwd = password
    if not pwd:
        pwd = getpass.getpass("Password: ")
        confirm = getpass.getpass("Confirm password: ")
        if pwd != confirm:
            print("Passwords do not match", file=sys.stderr)
            return 1
    _ensure_schema()
    session = get_session_factory()()
    try:
        user = create_user(
            session,
            email=email,
            password=pwd,
            display_name=display_name,
            role=role,
        )
        session.commit()
        print(f"Created user {user.email} (id={user.user_id}, role={user.role})")
        return 0
    except ValueError as exc:
        session.rollback()
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        print(f"create-user failed: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()


def seed_watchlist_cmd(
    *,
    path: Path | None,
    name: str | None,
    force: bool,
) -> int:
    """Seed the default (or named) watchlist from Research Fair Value Excel."""
    from pms_platform.watchlists.seed import (
        research_fair_value_watchlist_path,
        seed_watchlist,
    )
    from pms_platform.watchlists.service import WatchlistError

    source = path or research_fair_value_watchlist_path()
    if source is None:
        print(
            "Watchlist Excel not found. Pass --file or keep "
            "Research/Portfolio/Stocks_FairValue_Watchlist.xlsx on this device.",
            file=sys.stderr,
        )
        return 1
    _ensure_schema()
    session = get_session_factory()()
    try:
        result = seed_watchlist(session, path=source, name=name, force=force)
        session.commit()
        print(
            f"Seeded watchlist '{result.watchlist_name}' "
            f"(id={result.watchlist_id}): added {result.added}, "
            f"skipped {result.skipped}, names {result.names}"
        )
        return 0
    except WatchlistError as exc:
        session.rollback()
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        print(f"seed-watchlist failed: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()


def sync_insider_disclosures_cmd(days: int = 90) -> int:
    """Backfill BSE insider filings day-by-day into insider_disclosure_days."""
    from pms_platform.market_data.insider_store import sync_insider_days

    end = date.today()
    start = end - timedelta(days=max(1, days) - 1)
    _ensure_schema()
    session = get_session_factory()()
    try:
        fetched = sync_insider_days(session, start, end)
        session.commit()
        print(f"Insider days fetched from BSE: {fetched} ({start} .. {end})")
        return 0
    except Exception as exc:
        session.rollback()
        print(f"sync-insider-disclosures failed: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()


def seed_pivot_from_research_cmd(
    workbook: Path | None = None,
    *,
    include_history: bool = True,
) -> int:
    """Seed pivot portfolio (+ optional bhav history) from Research workbook."""
    from pms_platform.market_data.pivot_seed import seed_pivot_from_research

    _ensure_schema()
    session = get_session_factory()()
    try:
        result = seed_pivot_from_research(
            session, workbook=workbook, include_history=include_history
        )
        session.commit()
        print(
            f"Pivot seed: {result['portfolio_symbols']} portfolio symbols, "
            f"{result['days_committed']} bhav days committed, "
            f"{result.get('vol_exp_symbols', 0)} Vol Exp rows"
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        print(f"seed-pivot-from-research failed: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()


def harvest_portfolio_changes_cmd(
    *,
    apply: bool = False,
    workbook: Path | None = None,
) -> int:
    """Harvest Portfolio_*.xlsx Change notes into the transactions master."""
    from pms_platform.ingestion.portfolio_change_harvest import apply_harvest

    workbooks = [workbook] if workbook is not None else None
    result = apply_harvest(dry_run=not apply, workbooks=workbooks)
    present_fp = {t.fingerprint for t in result.already_present}
    missing = [t for t in result.candidates if t.fingerprint not in present_fp]

    print(f"Master: {result.master_path}")
    print(
        f"Candidates={len(result.candidates)} "
        f"already={len(result.already_present)} "
        f"missing={len(missing)}"
    )
    for trade in missing:
        print(
            f"  + {trade.event_date.isoformat()} {trade.portfolio_name} "
            f"{trade.event_type} {trade.quantity}@{trade.price} "
            f"← {trade.workbook_name}/{trade.sheet_name}"
        )
    if result.skipped:
        print(f"Skipped notes: {len(result.skipped)}")
        for line in result.skipped[:20]:
            print(f"  · {line}")
        if len(result.skipped) > 20:
            print(f"  … {len(result.skipped) - 20} more")
    if not apply:
        print("Dry run only. Pass --apply to append missing rows.")
        return 0
    print(f"Appended={len(result.appended)}")
    if result.backup_path:
        print(f"Backup: {result.backup_path}")
    if result.synced_raw:
        print(f"Synced raw: {result.synced_raw}")
    print("Reimport transactions (OneDrive refresh / import-all) to rebuild episodes.")
    return 0


def sync_bhav_day_cmd(file: Path) -> int:
    """Stage + validate + commit one NSE CM bhav file through the verification loop."""
    from pms_platform.market_data.nse_bhav_store import sync_bhav_file

    _ensure_schema()
    session = get_session_factory()()
    try:
        run = sync_bhav_file(session, Path(file))
        session.commit()
        print(
            f"Bhav run {run.run_id}: status={run.status} "
            f"date={run.trade_date} rows={run.row_count_all} eq={run.row_count_eq}"
        )
        if run.error_message:
            print(run.error_message, file=sys.stderr)
        return 0 if run.status == "committed" else 1
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        print(f"sync-bhav-day failed: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()


def fetch_bhav_day_cmd(
    trade_date: date | None,
    *,
    commit: bool,
    lookback_days: int = 0,
) -> int:
    """Download NSE CM-UDiFF Common Bhavcopy Final; optionally commit into the DB."""
    from pms_platform.market_data.nse_bhav_fetch import (
        BhavFetchError,
        download_cm_udiff_bhav,
        fetch_and_commit_cm_udiff_bhav,
    )

    if not commit:
        try:
            day, path = download_cm_udiff_bhav(trade_date, lookback_days=lookback_days)
        except BhavFetchError as exc:
            print(f"fetch-bhav-day failed: {exc}", file=sys.stderr)
            return 1
        print(f"Downloaded {day.isoformat()} (IST target) → {path}")
        return 0

    _ensure_schema()
    session = get_session_factory()()
    try:
        result = fetch_and_commit_cm_udiff_bhav(
            session, trade_date, lookback_days=lookback_days
        )
        session.commit()
        print(result["message"])
        if result.get("skipped"):
            return 0
        return 0 if result.get("status") == "committed" else 1
    except BhavFetchError as exc:
        session.rollback()
        print(f"fetch-bhav-day failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        print(f"fetch-bhav-day commit failed: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()


def main() -> None:
    """Parse CLI arguments and dispatch commands."""
    parser = argparse.ArgumentParser(description="PMS Decision Platform")
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_parser = subparsers.add_parser(
        "import-all", help="Import master files and export CSV outputs"
    )
    import_parser.add_argument(
        "--export-dir",
        type=Path,
        default=None,
        help="Directory for CSV exports (default: EXPORT_DIR from .env)",
    )

    snapshot_parser = subparsers.add_parser(
        "import-snapshots", help="Import portfolio snapshot workbooks"
    )
    snapshot_parser.add_argument(
        "--snapshot-dir",
        type=Path,
        default=None,
        help="Directory containing Portfolio_YYYY.xlsx files",
    )

    portfolio_parser = subparsers.add_parser(
        "portfolio-on", help="Reconstruct portfolio holdings on a date"
    )
    portfolio_parser.add_argument(
        "--date", type=_parse_date, required=True, help="ISO date, e.g. 2019-06-30"
    )
    portfolio_parser.add_argument("--export-dir", type=Path, default=None)

    reconcile_parser = subparsers.add_parser(
        "reconcile-snapshots",
        help="Compare reconstructed holdings against snapshot workbooks",
    )
    reconcile_parser.add_argument("--snapshot-dir", type=Path, default=None)
    reconcile_parser.add_argument("--export-dir", type=Path, default=None)

    market_import_parser = subparsers.add_parser(
        "import-market-data",
        help="Import canonical market-data CSV files from data/external",
    )
    market_import_parser.add_argument(
        "--external-dir",
        type=Path,
        default=None,
        help="Directory containing canonical market-data CSV files",
    )

    fundamentals_parser = subparsers.add_parser(
        "import-fundamentals",
        help="Import quarterly fundamentals CSV and recompute snapshots",
    )
    fundamentals_parser.add_argument("--external-dir", type=Path, default=None)
    fundamentals_parser.add_argument(
        "--provider",
        choices=["manual", "screener", "yahoo", "xbrl"],
        default=None,
        help="Fundamentals provider (default: FUNDAMENTALS_PROVIDER env)",
    )
    fundamentals_parser.add_argument(
        "--bse-all-securities",
        action="store_true",
        help="With --provider xbrl, fetch all security-master BSE codes (slow)",
    )
    fundamentals_parser.add_argument(
        "--yahoo-fallback",
        action="store_true",
        help="Also fetch Yahoo quarterly income statements after CSV import",
    )

    sync_watchlists_parser = subparsers.add_parser(
        "sync-watchlists",
        help="Refresh all watchlists: resolve symbols, fundamentals, SAST/insider alerts",
    )
    sync_watchlists_parser.add_argument("--external-dir", type=Path, default=None)
    sync_watchlists_parser.add_argument("--watchlist-id", type=int, default=None)
    sync_watchlists_parser.add_argument(
        "--skip-fundamentals",
        action="store_true",
        help="Skip fundamentals import (alerts-only refresh)",
    )

    refresh_fundamentals_parser = subparsers.add_parser(
        "refresh-watchlist-fundamentals",
        help="Scheduled job: BSE fetch + DB write + snapshot recompute (no alerts)",
    )
    refresh_fundamentals_parser.add_argument("--external-dir", type=Path, default=None)
    refresh_fundamentals_parser.add_argument("--watchlist-id", type=int, default=None)

    refresh_quotes_parser = subparsers.add_parser(
        "refresh-watchlist-quotes",
        help="Daily job: quotes + shareholding + materialized screener cache",
    )
    refresh_quotes_parser.add_argument("--watchlist-id", type=int, default=None)

    market_coverage_parser = subparsers.add_parser(
        "market-data-coverage",
        help="Export price and benchmark coverage reports",
    )
    market_coverage_parser.add_argument("--export-dir", type=Path, default=None)

    analyze_parser = subparsers.add_parser(
        "analyze-episodes",
        help="Compute closed-episode performance and export CSV outputs",
    )
    analyze_parser.add_argument("--export-dir", type=Path, default=None)

    live_parser = subparsers.add_parser(
        "refresh-live-quotes",
        help="Fetch live BSE quotes for open holdings (Indian Stock Market API)",
    )
    live_parser.add_argument(
        "--nse",
        action="store_true",
        help="Prefer NSE (.NS) instead of BSE (.BO)",
    )

    ca_parser = subparsers.add_parser(
        "build-corporate-actions",
        help="Fetch Yahoo split/bonus events and write corporate_actions.csv (Dad-replicable)",
    )
    ca_parser.add_argument("--output", type=Path, default=None)
    ca_parser.add_argument("--security-master", type=Path, default=None)
    ca_parser.add_argument("--transactions", type=Path, default=None)

    repair_parser = subparsers.add_parser(
        "repair-prices-yahoo",
        help="Replace a security's daily prices with Yahoo back-adjusted history (rights/splits)",
    )
    repair_parser.add_argument("--security-id", default=None)
    repair_parser.add_argument("--portfolio-name", default=None)
    repair_parser.add_argument(
        "--seed-csv",
        type=Path,
        default=None,
        help="Optional daily_prices.csv to rewrite (default: docker seed)",
    )

    create_user_parser = subparsers.add_parser(
        "create-user",
        help="Create an invite-only app user (first admin via CLI)",
    )
    create_user_parser.add_argument("--email", required=True)
    create_user_parser.add_argument("--name", required=True, help="Display name")
    create_user_parser.add_argument(
        "--role",
        choices=["admin", "member"],
        default="member",
    )
    create_user_parser.add_argument(
        "--password",
        default=None,
        help="Password (omit to prompt interactively)",
    )

    seed_watchlist_parser = subparsers.add_parser(
        "seed-watchlist",
        help="Seed a watchlist from Research Stocks_FairValue_Watchlist.xlsx",
    )
    seed_watchlist_parser.add_argument(
        "--from-research",
        action="store_true",
        help="Read Research/Portfolio/Stocks_FairValue_Watchlist.xlsx (default if --file is omitted)",
    )
    seed_watchlist_parser.add_argument(
        "--file",
        type=Path,
        default=None,
        help="Excel path (default: Research/Portfolio/Stocks_FairValue_Watchlist.xlsx)",
    )
    seed_watchlist_parser.add_argument(
        "--name",
        default=None,
        help="Watchlist to create or fill (default: existing default, else 'Fair Value')",
    )
    seed_watchlist_parser.add_argument(
        "--force",
        action="store_true",
        help="Add missing names when the target watchlist already has members",
    )

    insider_parser = subparsers.add_parser(
        "sync-insider-disclosures",
        help="Fetch BSE insider filings day-by-day and store them (BSE search is capped at 25 rows)",
    )
    insider_parser.add_argument(
        "--days",
        type=int,
        default=90,
        help="How many calendar days to backfill ending today (default 90)",
    )

    seed_pivot_parser = subparsers.add_parser(
        "seed-pivot-from-research",
        help="Seed pivot portfolio (+ optional history) from Research PivotPoints workbook",
    )
    seed_pivot_parser.add_argument(
        "--file",
        type=Path,
        default=None,
        help="Workbook path (default: Research/PivotPointsStrategy_*.xlsx)",
    )
    seed_pivot_parser.add_argument(
        "--portfolio-only",
        action="store_true",
        help="Only seed Portfolio sheet symbols (skip Daily/Last20Days ingest)",
    )

    harvest_parser = subparsers.add_parser(
        "harvest-portfolio-changes",
        help="Harvest Portfolio_*.xlsx Change notes into transactions master",
    )
    harvest_parser.add_argument(
        "--apply",
        action="store_true",
        help="Append missing Buy/Sell rows (default: dry-run)",
    )
    harvest_parser.add_argument(
        "--workbook",
        type=Path,
        default=None,
        help="Single Portfolio_YYYY.xlsx (default: all Research Portfolio_*.xlsx)",
    )

    sync_bhav_parser = subparsers.add_parser(
        "sync-bhav-day",
        help="Upload one NSE CM UDiFF bhav CSV/XLSX through validate→commit→reconcile",
    )
    sync_bhav_parser.add_argument(
        "--file",
        type=Path,
        required=True,
        help="Daily bhav CSV or XLSX path",
    )

    fetch_bhav_parser = subparsers.add_parser(
        "fetch-bhav-day",
        help="Download NSE CM-UDiFF Common Bhavcopy Final (today IST) and commit",
    )
    fetch_bhav_parser.add_argument(
        "--date",
        type=date.fromisoformat,
        default=None,
        help="Trade date YYYY-MM-DD IST (default: today IST only — no older fallback)",
    )
    fetch_bhav_parser.add_argument(
        "--lookback-days",
        type=int,
        default=0,
        help="Optional backfill only; scheduled jobs leave this at 0",
    )
    fetch_bhav_parser.add_argument(
        "--download-only",
        action="store_true",
        help="Save CSV under data/uploads/bhav/nse without committing",
    )

    args = parser.parse_args()
    if args.command == "import-all":
        raise SystemExit(import_all(args.export_dir))
    if args.command == "import-snapshots":
        raise SystemExit(import_snapshots(args.snapshot_dir))
    if args.command == "portfolio-on":
        raise SystemExit(portfolio_on_date(args.date, args.export_dir))
    if args.command == "reconcile-snapshots":
        raise SystemExit(reconcile_snapshots(args.snapshot_dir, args.export_dir))
    if args.command == "import-market-data":
        raise SystemExit(import_market_data_cmd(args.external_dir))
    if args.command == "import-fundamentals":
        raise SystemExit(
            import_fundamentals_cmd(
                args.external_dir,
                provider=args.provider,
                yahoo_fallback=args.yahoo_fallback,
                bse_all_securities=args.bse_all_securities,
            )
        )
    if args.command == "sync-watchlists":
        raise SystemExit(
            sync_watchlists_cmd(
                args.external_dir,
                watchlist_id=args.watchlist_id,
                skip_fundamentals=args.skip_fundamentals,
            )
        )
    if args.command == "refresh-watchlist-fundamentals":
        raise SystemExit(
            refresh_watchlist_fundamentals_cmd(
                args.external_dir,
                watchlist_id=args.watchlist_id,
            )
        )
    if args.command == "refresh-watchlist-quotes":
        raise SystemExit(
            refresh_watchlist_quotes_cmd(
                watchlist_id=args.watchlist_id,
            )
        )
    if args.command == "market-data-coverage":
        raise SystemExit(market_data_coverage(args.export_dir))
    if args.command == "analyze-episodes":
        raise SystemExit(analyze_episodes(args.export_dir))
    if args.command == "refresh-live-quotes":
        raise SystemExit(refresh_live_quotes_cmd(prefer_bse=not args.nse))
    if args.command == "build-corporate-actions":
        raise SystemExit(
            build_corporate_actions_cmd(
                output=args.output,
                security_master=args.security_master,
                transactions=args.transactions,
            )
        )
    if args.command == "repair-prices-yahoo":
        raise SystemExit(
            repair_prices_yahoo_cmd(
                security_id=args.security_id,
                portfolio_name=args.portfolio_name,
                seed_csv=args.seed_csv,
            )
        )
    if args.command == "create-user":
        raise SystemExit(
            create_user_cmd(
                email=args.email,
                display_name=args.name,
                role=args.role,
                password=args.password,
            )
        )
    if args.command == "seed-watchlist":
        raise SystemExit(
            seed_watchlist_cmd(path=args.file, name=args.name, force=args.force)
        )
    if args.command == "sync-insider-disclosures":
        raise SystemExit(sync_insider_disclosures_cmd(days=args.days))
    if args.command == "seed-pivot-from-research":
        raise SystemExit(
            seed_pivot_from_research_cmd(
                workbook=args.file,
                include_history=not args.portfolio_only,
            )
        )
    if args.command == "harvest-portfolio-changes":
        raise SystemExit(
            harvest_portfolio_changes_cmd(
                apply=args.apply,
                workbook=args.workbook,
            )
        )
    if args.command == "sync-bhav-day":
        raise SystemExit(sync_bhav_day_cmd(file=args.file))
    if args.command == "fetch-bhav-day":
        raise SystemExit(
            fetch_bhav_day_cmd(
                trade_date=args.date,
                commit=not args.download_only,
                lookback_days=args.lookback_days,
            )
        )


if __name__ == "__main__":
    main()
