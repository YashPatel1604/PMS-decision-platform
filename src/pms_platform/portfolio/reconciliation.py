"""Reconcile reconstructed holdings against historical snapshots."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.ingestion.snapshots import parse_snapshot_workbook
from pms_platform.models import Security
from pms_platform.portfolio.name_resolver import build_name_lookup, resolve_snapshot_security_id
from pms_platform.portfolio.position_engine import compute_quantities_as_of
from pms_platform.portfolio.types import ReconciliationMismatch

# From TRANSACTIONS_MASTER_V3 2012 Reconciliation Policy:
# soft window differences are warnings only; hard recon resumes 2012-08-27.
_SOFT_WINDOW_START = date(2012, 2, 17)
_SOFT_WINDOW_END = date(2012, 8, 7)
_ROUNDING_TOLERANCE_SHARES = 1


def classify_quantity_mismatch_severity(
    snapshot_date: date,
    reconstructed_quantity: int,
    snapshot_quantity: int,
) -> str | None:
    """Return ERROR/WARNING severity, or None when the mismatch is within policy tolerance."""
    difference = abs(reconstructed_quantity - snapshot_quantity)
    if difference == 0:
        return None
    if difference <= _ROUNDING_TOLERANCE_SHARES:
        return None
    if _SOFT_WINDOW_START <= snapshot_date <= _SOFT_WINDOW_END:
        return "WARNING"
    return "ERROR"


def reconcile_snapshot_workbook(
    session: Session,
    path: Path,
    as_of_date: date | None = None,
) -> list[ReconciliationMismatch]:
    """Compare reconstructed quantities to one workbook's snapshot rows."""
    securities = list(session.scalars(select(Security)).all())
    name_lookup = build_name_lookup(session)
    mismatches: list[ReconciliationMismatch] = []

    snapshot_rows = parse_snapshot_workbook(path)
    if as_of_date is not None:
        snapshot_rows = [row for row in snapshot_rows if row.snapshot_date == as_of_date]

    dates = sorted({row.snapshot_date for row in snapshot_rows})
    for snapshot_date in dates:
        rows_for_date = [row for row in snapshot_rows if row.snapshot_date == snapshot_date]
        reconstructed = compute_quantities_as_of(session, snapshot_date)

        snapshot_by_security: dict[str, tuple[int, str]] = {}
        for row in rows_for_date:
            security_id, resolved_name = resolve_snapshot_security_id(
                row.portfolio_name,
                securities,
                name_lookup,
            )
            if resolved_name == "LIQUID":
                continue
            if security_id is None:
                mismatches.append(
                    ReconciliationMismatch(
                        snapshot_date=snapshot_date,
                        security_id=None,
                        portfolio_name=row.portfolio_name,
                        reconstructed_quantity=0,
                        snapshot_quantity=row.quantity,
                        difference=-row.quantity,
                        source_file=row.source_file,
                        source_sheet=row.source_sheet,
                        severity="WARNING",
                        message=f"Unable to map snapshot label {row.portfolio_name!r} to Security Master",
                    )
                )
                continue
            snapshot_by_security[security_id] = (row.quantity, row.source_sheet)

        all_security_ids = set(reconstructed) | set(snapshot_by_security)
        for security_id in sorted(all_security_ids):
            recon_qty = reconstructed.get(security_id, 0)
            snap_qty = snapshot_by_security.get(security_id, (0, ""))[0]
            severity = classify_quantity_mismatch_severity(snapshot_date, recon_qty, snap_qty)
            if severity is None:
                continue

            portfolio_name = next(
                security.portfolio_name
                for security in securities
                if security.security_id == security_id
            )
            source_sheet = snapshot_by_security.get(
                security_id, (0, rows_for_date[0].source_sheet)
            )[1]
            if severity == "WARNING":
                message = (
                    f"Low-confidence 2012 snapshot mismatch for {portfolio_name} on "
                    f"{snapshot_date}: reconstructed={recon_qty}, snapshot={snap_qty}"
                )
            else:
                message = (
                    f"Quantity mismatch for {portfolio_name} on {snapshot_date}: "
                    f"reconstructed={recon_qty}, snapshot={snap_qty}"
                )
            mismatches.append(
                ReconciliationMismatch(
                    snapshot_date=snapshot_date,
                    security_id=security_id,
                    portfolio_name=portfolio_name,
                    reconstructed_quantity=recon_qty,
                    snapshot_quantity=snap_qty,
                    difference=recon_qty - snap_qty,
                    source_file=str(path),
                    source_sheet=source_sheet,
                    severity=severity,
                    message=message,
                )
            )

    return mismatches


def reconcile_all_snapshots(
    session: Session,
    directory: Path | None = None,
) -> list[ReconciliationMismatch]:
    """Reconcile all annual portfolio workbooks in a directory."""
    snapshot_dir = directory or Path("data/raw/portfolio_snapshots")
    mismatches: list[ReconciliationMismatch] = []
    for path in sorted(snapshot_dir.glob("Portfolio_*.xlsx")):
        mismatches.extend(reconcile_snapshot_workbook(session, path))
    return mismatches
