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


class MarketDataRefreshResponse(BaseModel):
    source_dir: str
    used_seed_fallback: bool
    missing_files: list[str]
    prices_inserted: int
    prices_skipped: int
    prices_unresolved: int
    prices_invalid: int
    dividends_inserted: int
    dividends_skipped: int
    dividends_unresolved: int
    dividends_invalid: int
    benchmarks_inserted: int
    benchmarks_skipped: int
    benchmarks_invalid: int
    successors_inserted: int
    successors_skipped: int
    successors_invalid: int
    notes: list[str]


class AnalysisRefreshResponse(BaseModel):
    ownership_ok: int
    ownership_insufficient: int
    post_exit_ok: int
    post_exit_insufficient: int
    cash_flow_rows: int


class OnedriveRefreshResponse(BaseModel):
    ok: bool
    error: str | None = None
    sync: SyncRawResponse
    reimport: ReimportResponse | None = None
    market_data: MarketDataRefreshResponse | None = None
    analysis: AnalysisRefreshResponse | None = None
    notes: list[str] = []


@router.post("/refresh-from-onedrive", response_model=OnedriveRefreshResponse)
def refresh_data_from_onedrive(
    session: Session = Depends(get_db),
) -> OnedriveRefreshResponse:
    """Copy latest Research workbooks into data/raw, reimport, market CSVs, analysis, NSE bhav.

    Reads the local RESEARCH_DIR mount (OneDrive files already on disk). Does not
    call the OneDrive cloud API — pin folders "Always keep on this device" first.
    """
    result = refresh_from_onedrive(session)
    reimport = None
    market_data = None
    analysis = None
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
    if result.market_data is not None:
        market_data = MarketDataRefreshResponse(
            source_dir=result.market_data.source_dir,
            used_seed_fallback=result.market_data.used_seed_fallback,
            missing_files=list(result.market_data.missing_files),
            prices_inserted=result.market_data.prices_inserted,
            prices_skipped=result.market_data.prices_skipped,
            prices_unresolved=result.market_data.prices_unresolved,
            prices_invalid=result.market_data.prices_invalid,
            dividends_inserted=result.market_data.dividends_inserted,
            dividends_skipped=result.market_data.dividends_skipped,
            dividends_unresolved=result.market_data.dividends_unresolved,
            dividends_invalid=result.market_data.dividends_invalid,
            benchmarks_inserted=result.market_data.benchmarks_inserted,
            benchmarks_skipped=result.market_data.benchmarks_skipped,
            benchmarks_invalid=result.market_data.benchmarks_invalid,
            successors_inserted=result.market_data.successors_inserted,
            successors_skipped=result.market_data.successors_skipped,
            successors_invalid=result.market_data.successors_invalid,
            notes=list(result.market_data.notes),
        )
    if result.analysis is not None:
        analysis = AnalysisRefreshResponse(
            ownership_ok=result.analysis.ownership_ok,
            ownership_insufficient=result.analysis.ownership_insufficient,
            post_exit_ok=result.analysis.post_exit_ok,
            post_exit_insufficient=result.analysis.post_exit_insufficient,
            cash_flow_rows=result.analysis.cash_flow_rows,
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
        market_data=market_data,
        analysis=analysis,
        notes=list(result.notes),
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
