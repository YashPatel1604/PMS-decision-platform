"""In-app Excel upload staging, validation, and commit pipeline."""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from pms_platform.analytics.first_buy_audit import build_first_buy_price_audit
from pms_platform.config import settings
from pms_platform.episodes.builder import build_episodes
from pms_platform.ingestion.common import file_checksum
from pms_platform.ingestion.securities import import_security_master
from pms_platform.ingestion.snapshots import (
    import_portfolio_snapshot_workbook,
    parse_snapshot_workbook,
)
from pms_platform.ingestion.transactions import import_transaction_master
from pms_platform.ingestion.validators import ValidationSeverity, validate_imported_data
from pms_platform.models import ImportBatch
from pms_platform.models.enums import EpisodeStatus
from pms_platform.portfolio.reconciliation import reconcile_snapshot_workbook

UPLOAD_KINDS = frozenset({"transactions", "security_master", "portfolio_snapshots"})

KIND_TO_SOURCE_TYPE = {
    "transactions": "upload_transactions",
    "security_master": "upload_security_master",
    "portfolio_snapshots": "upload_portfolio_snapshots",
}

KIND_TO_FILENAME = {
    "transactions": "MASTER_TRANSACTIONS_V1.xlsx",
    "security_master": "SECURITY_MASTER_V1.xlsx",
    "portfolio_snapshots": "Portfolio_upload.xlsx",
}


@dataclass(frozen=True)
class UploadIssue:
    severity: str
    code: str
    message: str
    security_id: str | None = None
    source_key: str | None = None
    event_date: str | None = None


@dataclass(frozen=True)
class UploadBatchState:
    batch_id: int
    kind: str
    status: str
    source_file: str
    source_checksum: str
    issues: tuple[UploadIssue, ...]
    error_count: int
    warning_count: int
    review_count: int
    row_counts: dict[str, int]
    episode_summary: dict[str, int] | None
    can_commit: bool
    notes: str | None


def _batch_dir(batch_id: int) -> Path:
    path = settings.upload_dir / str(batch_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _metadata_path(batch_id: int) -> Path:
    return _batch_dir(batch_id) / "metadata.json"


def _write_metadata(batch_id: int, payload: dict) -> None:
    _metadata_path(batch_id).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _read_metadata(batch_id: int) -> dict:
    path = _metadata_path(batch_id)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _issue_from_validation(issue) -> UploadIssue:
    return UploadIssue(
        severity=str(issue.severity),
        code=issue.code,
        message=issue.message,
        security_id=issue.security_id,
        source_key=issue.source_key,
        event_date=issue.event_date.isoformat() if issue.event_date else None,
    )


def _issue_from_mismatch(mismatch) -> UploadIssue:
    return UploadIssue(
        severity=mismatch.severity,
        code="SNAPSHOT_RECON_MISMATCH",
        message=mismatch.message,
        security_id=mismatch.security_id,
        source_key=f"{mismatch.source_file}|{mismatch.source_sheet}",
        event_date=mismatch.snapshot_date.isoformat(),
    )


def _count_issues(issues: list[UploadIssue]) -> tuple[int, int, int]:
    errors = sum(1 for issue in issues if issue.severity == "ERROR")
    warnings = sum(1 for issue in issues if issue.severity == "WARNING")
    reviews = sum(1 for issue in issues if issue.severity == "REVIEW")
    return errors, warnings, reviews


def _state_from_batch(batch: ImportBatch, metadata: dict) -> UploadBatchState:
    issues = [UploadIssue(**item) for item in metadata.get("issues", [])]
    errors, warnings, reviews = _count_issues(issues)
    return UploadBatchState(
        batch_id=batch.import_batch_id,
        kind=metadata.get("kind", batch.source_type.replace("upload_", "")),
        status=batch.status,
        source_file=batch.source_file,
        source_checksum=batch.source_checksum,
        issues=tuple(issues),
        error_count=errors,
        warning_count=warnings,
        review_count=reviews,
        row_counts=metadata.get("row_counts", {}),
        episode_summary=metadata.get("episode_summary"),
        can_commit=batch.status in {"validated", "staged"} and errors == 0,
        notes=batch.notes,
    )


def stage_upload(
    session: Session,
    *,
    kind: str,
    filename: str,
    content: bytes,
) -> UploadBatchState:
    """Persist an uploaded Excel workbook and create a staged batch."""
    if kind not in UPLOAD_KINDS:
        msg = f"Unsupported upload kind: {kind}"
        raise ValueError(msg)
    if not filename.lower().endswith((".xlsx", ".xlsm")):
        msg = "Only Excel workbooks (.xlsx / .xlsm) are accepted"
        raise ValueError(msg)

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    staging_name = KIND_TO_FILENAME[kind]
    if kind == "portfolio_snapshots" and filename.lower().startswith("portfolio_"):
        staging_name = Path(filename).name

    temp_token = uuid.uuid4().hex
    temp_path = settings.upload_dir / f"_incoming_{temp_token}_{staging_name}"
    temp_path.write_bytes(content)
    checksum = file_checksum(temp_path)

    batch = ImportBatch(
        source_type=KIND_TO_SOURCE_TYPE[kind],
        source_file=str(temp_path),
        source_checksum=checksum,
        status="staged",
        notes="Awaiting validation",
    )
    session.add(batch)
    session.flush()

    final_path = _batch_dir(batch.import_batch_id) / staging_name
    shutil.move(str(temp_path), final_path)
    batch.source_file = str(final_path)
    session.flush()

    metadata = {
        "kind": kind,
        "original_filename": filename,
        "issues": [],
        "row_counts": {},
        "episode_summary": None,
    }
    _write_metadata(batch.import_batch_id, metadata)
    session.commit()
    return _state_from_batch(batch, metadata)


def get_upload_batch(session: Session, batch_id: int) -> UploadBatchState:
    batch = session.get(ImportBatch, batch_id)
    if batch is None or not str(batch.source_type).startswith("upload_"):
        msg = f"Upload batch {batch_id} not found"
        raise KeyError(msg)
    return _state_from_batch(batch, _read_metadata(batch_id))


def _validate_transactions_or_securities(
    session: Session,
    kind: str,
    path: Path,
) -> tuple[list[UploadIssue], dict[str, int]]:
    issues: list[UploadIssue] = []
    row_counts: dict[str, int] = {}
    nested = session.begin_nested()
    try:
        if kind == "security_master":
            result = import_security_master(session, path)
            row_counts = {
                "inserted": result.inserted,
                "updated": result.updated,
                "skipped": result.skipped,
            }
        else:
            result = import_transaction_master(session, path)
            row_counts = {
                "equity_inserted": result.equity_inserted,
                "equity_skipped": result.equity_skipped,
                "liquid_inserted": result.liquid_inserted,
                "liquid_skipped": result.liquid_skipped,
                "summary_rows_skipped": result.summary_rows_skipped,
            }

        for issue in validate_imported_data(session):
            issues.append(_issue_from_validation(issue))

        if kind == "transactions":
            try:
                build_episodes(session)
                for row in build_first_buy_price_audit(session):
                    if row.status == "REVIEW":
                        issues.append(
                            UploadIssue(
                                severity="REVIEW",
                                code="FIRST_BUY_PRICE_REVIEW",
                                message=row.note or "First-buy price unit needs review",
                                security_id=row.security_id,
                            )
                        )
            except Exception as exc:  # noqa: BLE001 - surface as validation issue
                issues.append(
                    UploadIssue(
                        severity="WARNING",
                        code="EPISODE_BUILD_PREVIEW_FAILED",
                        message=str(exc),
                    )
                )
    finally:
        nested.rollback()
    return issues, row_counts


def _validate_snapshots(session: Session, path: Path) -> tuple[list[UploadIssue], dict[str, int]]:
    issues: list[UploadIssue] = []
    try:
        rows = parse_snapshot_workbook(path)
    except Exception as exc:  # noqa: BLE001
        return (
            [
                UploadIssue(
                    severity="ERROR",
                    code="SNAPSHOT_PARSE_FAILED",
                    message=str(exc),
                )
            ],
            {},
        )

    row_counts = {"snapshot_rows": len(rows)}
    for mismatch in reconcile_snapshot_workbook(session, path):
        issues.append(_issue_from_mismatch(mismatch))
    if not rows:
        issues.append(
            UploadIssue(
                severity="WARNING",
                code="SNAPSHOT_EMPTY",
                message="No snapshot rows were parsed from the workbook",
            )
        )
    return issues, row_counts


def validate_workbook_import(
    session: Session, *, kind: str, path: Path
) -> tuple[list[UploadIssue], dict[str, int]]:
    """Dry-run validation for a workbook on disk (nested transaction rollback)."""
    if kind not in UPLOAD_KINDS:
        msg = f"Unsupported upload kind: {kind}"
        raise ValueError(msg)
    if kind in {"transactions", "security_master"}:
        return _validate_transactions_or_securities(session, kind, path)
    return _validate_snapshots(session, path)


def commit_workbook_import(
    session: Session, *, kind: str, path: Path
) -> tuple[dict[str, int], dict[str, int] | None]:
    """Apply a validated workbook into Postgres."""
    if kind not in UPLOAD_KINDS:
        msg = f"Unsupported upload kind: {kind}"
        raise ValueError(msg)
    if not path.exists():
        msg = f"Workbook not found: {path}"
        raise FileNotFoundError(msg)

    episode_summary: dict[str, int] | None = None
    if kind == "security_master":
        result = import_security_master(session, path)
        row_counts = {
            "inserted": result.inserted,
            "updated": result.updated,
            "skipped": result.skipped,
        }
        for issue in validate_imported_data(session):
            if issue.severity == ValidationSeverity.ERROR:
                raise ValueError(issue.message)
    elif kind == "transactions":
        result = import_transaction_master(session, path)
        row_counts = {
            "equity_inserted": result.equity_inserted,
            "equity_skipped": result.equity_skipped,
            "liquid_inserted": result.liquid_inserted,
            "liquid_skipped": result.liquid_skipped,
            "summary_rows_skipped": result.summary_rows_skipped,
        }
        validation = validate_imported_data(session)
        hard_errors = [
            issue for issue in validation if issue.severity == ValidationSeverity.ERROR
        ]
        if hard_errors:
            raise ValueError(hard_errors[0].message)
        episodes, _ = build_episodes(session)
        open_count = sum(1 for episode in episodes if episode.status == EpisodeStatus.OPEN.value)
        closed_count = sum(
            1 for episode in episodes if episode.status == EpisodeStatus.CLOSED.value
        )
        episode_summary = {
            "episodes": len(episodes),
            "open": open_count,
            "closed": closed_count,
        }
    else:
        result = import_portfolio_snapshot_workbook(session, path)
        row_counts = {
            "inserted": result.inserted,
            "skipped": result.skipped,
            "unresolved_names": result.unresolved_names,
        }
        recon_issues = [
            _issue_from_mismatch(item) for item in reconcile_snapshot_workbook(session, path)
        ]
        hard = [issue for issue in recon_issues if issue.severity == "ERROR"]
        if hard:
            raise ValueError(hard[0].message)

    return row_counts, episode_summary


def validate_upload(session: Session, batch_id: int) -> UploadBatchState:
    """Dry-run checks against the staged workbook."""
    batch = session.get(ImportBatch, batch_id)
    if batch is None or not str(batch.source_type).startswith("upload_"):
        msg = f"Upload batch {batch_id} not found"
        raise KeyError(msg)

    metadata = _read_metadata(batch_id)
    kind = metadata.get("kind")
    path = Path(batch.source_file)
    if kind not in UPLOAD_KINDS:
        msg = f"Unknown upload kind for batch {batch_id}"
        raise ValueError(msg)
    if not path.exists():
        msg = f"Staged file missing for batch {batch_id}"
        raise FileNotFoundError(msg)

    issues, row_counts = validate_workbook_import(session, kind=kind, path=path)

    errors, warnings, reviews = _count_issues(issues)
    metadata["issues"] = [asdict(issue) for issue in issues]
    metadata["row_counts"] = row_counts
    _write_metadata(batch_id, metadata)

    batch.status = "validated" if errors == 0 else "validation_failed"
    batch.notes = (
        f"Validation complete: {errors} error(s), {warnings} warning(s), "
        f"{reviews} review item(s)"
    )
    session.commit()
    return _state_from_batch(batch, metadata)


def commit_upload(session: Session, batch_id: int) -> UploadBatchState:
    """Apply a validated upload into the live system."""
    batch = session.get(ImportBatch, batch_id)
    if batch is None or not str(batch.source_type).startswith("upload_"):
        msg = f"Upload batch {batch_id} not found"
        raise KeyError(msg)

    metadata = _read_metadata(batch_id)
    kind = metadata.get("kind")
    path = Path(batch.source_file)
    issues = [UploadIssue(**item) for item in metadata.get("issues", [])]
    errors, _, _ = _count_issues(issues)
    if batch.status == "validation_failed" or errors > 0:
        msg = "Cannot commit upload with validation errors"
        raise ValueError(msg)
    if batch.status not in {"staged", "validated"}:
        msg = f"Upload batch {batch_id} is not ready to commit (status={batch.status})"
        raise ValueError(msg)
    if not path.exists():
        msg = f"Staged file missing for batch {batch_id}"
        raise FileNotFoundError(msg)

    # Re-validate just before commit when the user skipped an explicit validate call.
    if batch.status == "staged":
        validate_upload(session, batch_id)
        batch = session.get(ImportBatch, batch_id)
        assert batch is not None
        metadata = _read_metadata(batch_id)
        issues = [UploadIssue(**item) for item in metadata.get("issues", [])]
        errors, _, _ = _count_issues(issues)
        if errors > 0:
            msg = "Cannot commit upload with validation errors"
            raise ValueError(msg)

    try:
        row_counts, episode_summary = commit_workbook_import(session, kind=kind, path=path)
        metadata["row_counts"] = row_counts
        metadata["episode_summary"] = episode_summary
        if kind == "portfolio_snapshots":
            recon_issues = [
                _issue_from_mismatch(item) for item in reconcile_snapshot_workbook(session, path)
            ]
            metadata["issues"] = [asdict(issue) for issue in recon_issues]
        _write_metadata(batch_id, metadata)
        batch.status = "committed"
        batch.notes = f"Committed on {date.today().isoformat()}"
        session.commit()
    except Exception:
        session.rollback()
        batch = session.get(ImportBatch, batch_id)
        if batch is not None:
            batch.status = "commit_failed"
            batch.notes = "Commit failed; database changes were rolled back"
            session.commit()
        raise

    return _state_from_batch(batch, metadata)
