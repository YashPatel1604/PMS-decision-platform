"""CLI entry point for the PMS decision platform."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

from pms_platform.config import settings
from pms_platform.db.base import get_session_factory
from pms_platform.episodes.builder import build_episodes
from pms_platform.ingestion.exports import (
    export_decision_events_csv,
    export_episodes_csv,
    export_validation_report_csv,
)
from pms_platform.ingestion.securities import import_security_master
from pms_platform.ingestion.transactions import import_transaction_master
from pms_platform.ingestion.validators import ValidationSeverity, validate_imported_data


def _ensure_schema() -> None:
    """Apply Alembic migrations before importing data."""
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(alembic_cfg, "head")


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


def main() -> None:
    """Parse CLI arguments and dispatch commands."""
    parser = argparse.ArgumentParser(description="PMS Decision Platform")
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_parser = subparsers.add_parser("import-all", help="Import master files and export CSV outputs")
    import_parser.add_argument(
        "--export-dir",
        type=Path,
        default=None,
        help="Directory for CSV exports (default: EXPORT_DIR from .env)",
    )

    args = parser.parse_args()
    if args.command == "import-all":
        raise SystemExit(import_all(args.export_dir))


if __name__ == "__main__":
    main()
