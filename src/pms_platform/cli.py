"""CLI entry point for the PMS decision platform."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from alembic import command
from alembic.config import Config

from pms_platform.analytics.exports import (
    export_episode_cash_flows_csv,
    export_episode_performance_csv,
    export_post_exit_performance_csv,
    export_sell_assessments_csv,
    export_sell_since_workbook,
)
from pms_platform.analytics.service import run_full_episode_analysis
from pms_platform.config import settings
from pms_platform.db.base import get_session_factory
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
    _ensure_schema()
    session = get_session_factory()()
    try:
        result = import_portfolio_snapshots(
            session, snapshot_dir or settings.raw_data_dir / "portfolio_snapshots"
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
        print(f"  Excel workbook: {(output_dir / 'sell_since_analysis.xlsx').resolve()}")
        return 0
    except Exception as exc:
        session.rollback()
        print(f"Episode analysis failed: {exc}", file=sys.stderr)
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
    if args.command == "market-data-coverage":
        raise SystemExit(market_data_coverage(args.export_dir))
    if args.command == "analyze-episodes":
        raise SystemExit(analyze_episodes(args.export_dir))


if __name__ == "__main__":
    main()
