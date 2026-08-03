"""Clear checksum-gated imports and reload from data/raw after a OneDrive sync."""

from __future__ import annotations

from alembic import command
from alembic.config import Config

from pms_platform.config import settings
from pms_platform.db.base import get_session_factory
from pms_platform.ingestion.exports import (
    export_decision_events_csv,
    export_episodes_csv,
    export_reconciliation_report_csv,
    export_validation_report_csv,
)
from pms_platform.ingestion.onedrive_refresh import reimport_from_raw
from pms_platform.ingestion.validators import validate_imported_data
from pms_platform.portfolio.reconciliation import reconcile_all_snapshots


def _ensure_schema() -> None:
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(alembic_cfg, "head")


def main() -> int:
    _ensure_schema()
    raw = settings.raw_data_dir
    snapshot_dir = raw / "portfolio_snapshots"
    export_dir = settings.export_dir

    session = get_session_factory()()
    try:
        result = reimport_from_raw(session)
        if result.validation_errors:
            issues = validate_imported_data(session)
            export_validation_report_csv(issues, export_dir / "validation_report.csv")
            print(
                f"Validation failed with {result.validation_errors} error(s). "
                "See validation_report.csv"
            )
            return 1

        export_episodes_csv(session, export_dir / "investment_episodes.csv")
        export_decision_events_csv(session, export_dir / "decision_events.csv")
        issues = validate_imported_data(session)
        export_validation_report_csv(issues, export_dir / "validation_report.csv")

        mismatches = reconcile_all_snapshots(session, snapshot_dir)
        export_reconciliation_report_csv(mismatches, export_dir / "reconciliation_report.csv")
        recon_errors = [m for m in mismatches if m.severity == "ERROR"]
        recon_warnings = [m for m in mismatches if m.severity == "WARNING"]
        post_2017 = [m for m in recon_errors if m.snapshot_date.year > 2017]

        print("Reimport complete.")
        print(f"  Securities: inserted={result.securities_inserted}")
        print(f"  Equity txns: inserted={result.equity_txns_inserted}")
        print(f"  Liquid txns: inserted={result.liquid_txns_inserted}")
        print(f"  Episodes: {result.episodes}")
        print(f"  Decision events: {result.decision_events}")
        print(
            f"  Snapshots: inserted={result.snapshots_inserted}, "
            f"unresolved={result.snapshots_unresolved}"
        )
        print(
            f"  Reconciliation: errors={len(recon_errors)} "
            f"(post-2017={len(post_2017)}), warnings={len(recon_warnings)}"
        )
        print(f"  Exports: {export_dir.resolve()}")
        return 0
    except Exception as exc:
        session.rollback()
        print(f"Reimport failed: {exc}")
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
