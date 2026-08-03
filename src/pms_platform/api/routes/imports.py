"""Excel upload and calibration API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from pms_platform.api.routes.episodes import get_db
from pms_platform.ingestion.onedrive_refresh import refresh_from_onedrive
from pms_platform.ingestion.upload_pipeline import (
    UPLOAD_KINDS,
    commit_upload,
    get_upload_batch,
    stage_upload,
    validate_upload,
)

router = APIRouter()


class SyncRawResponse(BaseModel):
    copied: list[str]
    snapshot_count: int
    research_dir: str | None
    notes: list[str]


class ReimportResponse(BaseModel):
    securities_inserted: int
    equity_txns_inserted: int
    liquid_txns_inserted: int
    episodes: int
    decision_events: int
    snapshots_inserted: int
    snapshots_unresolved: int
    validation_errors: int
    notes: list[str]


class OnedriveRefreshResponse(BaseModel):
    ok: bool
    error: str | None = None
    sync: SyncRawResponse
    reimport: ReimportResponse | None = None


@router.post("/refresh-from-onedrive", response_model=OnedriveRefreshResponse)
def refresh_data_from_onedrive(
    session: Session = Depends(get_db),
) -> OnedriveRefreshResponse:
    """Copy latest Research/OneDrive workbooks into data/raw and fully reimport.

    Does not watch OneDrive automatically — call this after source files change.
    """
    result = refresh_from_onedrive(session)
    reimport = None
    if result.reimport is not None:
        reimport = ReimportResponse(
            securities_inserted=result.reimport.securities_inserted,
            equity_txns_inserted=result.reimport.equity_txns_inserted,
            liquid_txns_inserted=result.reimport.liquid_txns_inserted,
            episodes=result.reimport.episodes,
            decision_events=result.reimport.decision_events,
            snapshots_inserted=result.reimport.snapshots_inserted,
            snapshots_unresolved=result.reimport.snapshots_unresolved,
            validation_errors=result.reimport.validation_errors,
            notes=list(result.reimport.notes),
        )
    response = OnedriveRefreshResponse(
        ok=result.ok,
        error=result.error,
        sync=SyncRawResponse(
            copied=list(result.sync.copied),
            snapshot_count=result.sync.snapshot_count,
            research_dir=result.sync.research_dir,
            notes=list(result.sync.notes),
        ),
        reimport=reimport,
    )
    return response


class UploadIssueResponse(BaseModel):
    severity: str
    code: str
    message: str
    security_id: str | None = None
    source_key: str | None = None
    event_date: str | None = None


class UploadBatchResponse(BaseModel):
    batch_id: int
    kind: str
    status: str
    source_file: str
    source_checksum: str
    issues: list[UploadIssueResponse]
    error_count: int
    warning_count: int
    review_count: int
    row_counts: dict[str, int]
    episode_summary: dict[str, int] | None
    can_commit: bool
    notes: str | None


def _batch_response(state) -> UploadBatchResponse:
    return UploadBatchResponse(
        batch_id=state.batch_id,
        kind=state.kind,
        status=state.status,
        source_file=state.source_file,
        source_checksum=state.source_checksum,
        issues=[
            UploadIssueResponse(
                severity=issue.severity,
                code=issue.code,
                message=issue.message,
                security_id=issue.security_id,
                source_key=issue.source_key,
                event_date=issue.event_date,
            )
            for issue in state.issues
        ],
        error_count=state.error_count,
        warning_count=state.warning_count,
        review_count=state.review_count,
        row_counts=state.row_counts,
        episode_summary=state.episode_summary,
        can_commit=state.can_commit,
        notes=state.notes,
    )


@router.post("/upload", response_model=UploadBatchResponse)
async def upload_excel(
    kind: str = Form(...),
    file: UploadFile = File(...),
    session: Session = Depends(get_db),
) -> UploadBatchResponse:
    """Stage an Excel workbook for validation and later commit."""
    if kind not in UPLOAD_KINDS:
        raise HTTPException(
            status_code=400,
            detail=(
                "kind must be one of: transactions, security_master, portfolio_snapshots"
            ),
        )
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    try:
        state = stage_upload(
            session,
            kind=kind,
            filename=file.filename or "upload.xlsx",
            content=content,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _batch_response(state)


@router.post("/{batch_id}/validate", response_model=UploadBatchResponse)
def validate_excel_batch(
    batch_id: int,
    session: Session = Depends(get_db),
) -> UploadBatchResponse:
    """Run dry-run validation and calibration checks for a staged upload."""
    try:
        state = validate_upload(session, batch_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _batch_response(state)


@router.post("/{batch_id}/commit", response_model=UploadBatchResponse)
def commit_excel_batch(
    batch_id: int,
    session: Session = Depends(get_db),
) -> UploadBatchResponse:
    """Commit a validated upload into the live database."""
    try:
        state = commit_upload(session, batch_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return _batch_response(state)


@router.get("/{batch_id}", response_model=UploadBatchResponse)
def get_excel_batch(
    batch_id: int,
    session: Session = Depends(get_db),
) -> UploadBatchResponse:
    """Return the current status and issue list for an upload batch."""
    try:
        state = get_upload_batch(session, batch_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _batch_response(state)
