"""CLI entry point for the PMS decision platform."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from alembic import command
from alembic.config import Config

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

    args = parser.parse_args()
    if args.command == "import-all":
        raise SystemExit(import_all(args.export_dir))
    if args.command == "import-snapshots":
        raise SystemExit(import_snapshots(args.snapshot_dir))
    if args.command == "portfolio-on":
        raise SystemExit(portfolio_on_date(args.date, args.export_dir))
    if args.command == "reconcile-snapshots":
        raise SystemExit(reconcile_snapshots(args.snapshot_dir, args.export_dir))


if __name__ == "__main__":
    main()
