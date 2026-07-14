#!/usr/bin/env python3
"""Clear checksum-gated imports and reload from data/raw after a OneDrive sync."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import delete

from pms_platform.config import settings
from pms_platform.db.base import get_session_factory
from pms_platform.episodes.builder import build_episodes
from pms_platform.ingestion.exports import (
    export_decision_events_csv,
    export_episodes_csv,
    export_reconciliation_report_csv,
    export_validation_report_csv,
)
from pms_platform.ingestion.securities import import_security_master
from pms_platform.ingestion.snapshots import clear_portfolio_snapshots, import_portfolio_snapshots
from pms_platform.ingestion.transactions import import_transaction_master
from pms_platform.ingestion.validators import ValidationSeverity, validate_imported_data
from pms_platform.models import (
    DecisionEvent,
    ImportBatch,
    InvestmentEpisode,
    LiquidTransaction,
    Security,
    Transaction,
)
from pms_platform.portfolio.reconciliation import reconcile_all_snapshots


def _ensure_schema() -> None:
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(alembic_cfg, "head")


def main() -> int:
    _ensure_schema()
    raw = settings.raw_data_dir
    security_path = raw / "security_master" / "SECURITY_MASTER_V1.xlsx"
    transaction_path = raw / "transactions" / "MASTER_TRANSACTIONS_V1.xlsx"
    snapshot_dir = raw / "portfolio_snapshots"
    export_dir = settings.export_dir

    session = get_session_factory()()
    try:
        session.execute(delete(DecisionEvent))
        session.execute(delete(InvestmentEpisode))
        session.execute(delete(Transaction))
        session.execute(delete(LiquidTransaction))
        clear_portfolio_snapshots(session)
        session.execute(delete(Security))
        session.execute(
            delete(ImportBatch).where(
                ImportBatch.source_type.in_(["transactions", "securities", "snapshots"])
            )
        )
        session.commit()

        sec = import_security_master(session, security_path)
        txn = import_transaction_master(session, transaction_path)
        issues = validate_imported_data(session)
        errors = [i for i in issues if i.severity == ValidationSeverity.ERROR]
        if errors:
            export_validation_report_csv(issues, export_dir / "validation_report.csv")
            session.commit()
            print(f"Validation failed with {len(errors)} error(s). See validation_report.csv")
            return 1

        episodes, decisions = build_episodes(session)
        snap = import_portfolio_snapshots(session, snapshot_dir)
        session.commit()

        export_episodes_csv(session, export_dir / "investment_episodes.csv")
        export_decision_events_csv(session, export_dir / "decision_events.csv")
        export_validation_report_csv(issues, export_dir / "validation_report.csv")

        mismatches = reconcile_all_snapshots(session, snapshot_dir)
        export_reconciliation_report_csv(mismatches, export_dir / "reconciliation_report.csv")
        recon_errors = [m for m in mismatches if m.severity == "ERROR"]
        recon_warnings = [m for m in mismatches if m.severity == "WARNING"]
        post_2017 = [m for m in recon_errors if m.snapshot_date.year > 2017]

        print("Reimport complete.")
        print(f"  Securities: inserted={sec.inserted}")
        print(f"  Equity txns: inserted={txn.equity_inserted}")
        print(f"  Liquid txns: inserted={txn.liquid_inserted}")
        print(f"  Episodes: {len(episodes)}")
        print(f"  Decision events: {len(decisions)}")
        print(f"  Snapshots: inserted={snap.inserted}, unresolved={snap.unresolved_names}")
        print(f"  Reconciliation: errors={len(recon_errors)} (post-2017={len(post_2017)}), warnings={len(recon_warnings)}")
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
