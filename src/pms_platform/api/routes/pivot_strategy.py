"""Pivot Point Strategy: bhav upload loop + dashboard API."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from pms_platform.api.deps_read_context import read_context_from_query
from pms_platform.api.routes.episodes import get_db
from pms_platform.approval.service import (
    ApprovalError,
    submit_request,
    upsert_pivot_selection_draft,
)
from pms_platform.domain.pivot_selection import (
    replace_official_selection,
    resolve_selection,
    selection_row_version,
)
from pms_platform.feature_flags import approval_workflow_enabled
from pms_platform.read_context import ReadContext
from pms_platform.market_data.nse_bhav_fetch import (
    BhavFetchError,
    fetch_and_commit_cm_udiff_bhav,
)
from pms_platform.market_data.nse_bhav_parse import BhavParseError
from pms_platform.market_data.nse_bhav_store import (
    commit_bhav_run,
    delete_portfolio_symbol,
    get_bhav_run,
    known_bhav_symbols,
    search_bhav_symbols,
    stage_bhav_upload,
    upsert_portfolio_symbols,
    validate_bhav_run,
)
from pms_platform.market_data.pivot_dashboard import HIDDEN_PIVOT_SYMBOLS, build_pivot_dashboard
from pms_platform.models.nse_bhav import PivotPortfolioSymbol
from sqlalchemy import select

router = APIRouter()


class BhavRunResponse(BaseModel):
    run_id: int
    trade_date: date | None
    status: str
    source_filename: str
    source_checksum: str
    row_count_all: int
    row_count_eq: int
    validation_report: dict
    reconcile_report: dict
    error_message: str | None = None


class PortfolioMemberIn(BaseModel):
    symbol: str
    dummy: bool = False
    portfolio_a: bool = False
    uptrend: bool = False
    support_note: str | None = None
    buy_note: str | None = None
    sma_50: str | None = None
    sma_100: str | None = None
    sma_200: str | None = None
    notes: str | None = None


class PortfolioReplaceRequest(BaseModel):
    members: list[PortfolioMemberIn] = Field(default_factory=list)


class AddFirmRequest(BaseModel):
    symbol: str


class SelectionReplaceRequest(BaseModel):
    symbols: list[str] = Field(default_factory=list)


def _user(request: Request):
    return getattr(request.state, "user", None)


def _run_response(run) -> BhavRunResponse:
    return BhavRunResponse(
        run_id=run.run_id,
        trade_date=run.trade_date,
        status=run.status,
        source_filename=run.source_filename,
        source_checksum=run.source_checksum,
        row_count_all=run.row_count_all,
        row_count_eq=run.row_count_eq,
        validation_report=run.validation_report or {},
        reconcile_report=run.reconcile_report or {},
        error_message=run.error_message,
    )


class FetchBhavResponse(BaseModel):
    skipped: bool
    trade_date: date | None
    message: str
    run_id: int | None = None
    status: str | None = None
    row_count_all: int | None = None
    row_count_eq: int | None = None


@router.post("/bhav/fetch-nse", response_model=FetchBhavResponse)
def fetch_nse_bhav(
    trade_date: date | None = Query(default=None),
    session: Session = Depends(get_db),
) -> FetchBhavResponse:
    """Pull CM-UDiFF Common Bhavcopy Final from NSE and commit (today IST by default)."""
    try:
        result = fetch_and_commit_cm_udiff_bhav(session, trade_date)
    except BhavFetchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (BhavParseError, ValueError, LookupError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.commit()
    if result.get("status") not in {"committed", "skipped"}:
        raise HTTPException(status_code=400, detail=str(result.get("message")))
    return FetchBhavResponse(
        skipped=bool(result["skipped"]),
        trade_date=result["trade_date"],  # type: ignore[arg-type]
        message=str(result["message"]),
        run_id=result["run_id"],  # type: ignore[arg-type]
        status=result["status"],  # type: ignore[arg-type]
        row_count_all=result["row_count_all"],  # type: ignore[arg-type]
        row_count_eq=result["row_count_eq"],  # type: ignore[arg-type]
    )


@router.post("/bhav/upload", response_model=BhavRunResponse)
async def upload_bhav(
    file: UploadFile = File(...),
    session: Session = Depends(get_db),
) -> BhavRunResponse:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    run = stage_bhav_upload(
        session,
        filename=file.filename or "bhav.csv",
        content=content,
    )
    session.commit()
    return _run_response(run)


@router.post("/bhav/{run_id}/validate", response_model=BhavRunResponse)
def validate_bhav(run_id: int, session: Session = Depends(get_db)) -> BhavRunResponse:
    try:
        run = validate_bhav_run(session, run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BhavParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.commit()
    return _run_response(run)


@router.post("/bhav/{run_id}/commit", response_model=BhavRunResponse)
def commit_bhav(run_id: int, session: Session = Depends(get_db)) -> BhavRunResponse:
    try:
        run = commit_bhav_run(session, run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (BhavParseError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.commit()
    return _run_response(run)


@router.get("/bhav/{run_id}", response_model=BhavRunResponse)
def get_bhav(run_id: int, session: Session = Depends(get_db)) -> BhavRunResponse:
    run = get_bhav_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Unknown bhav run")
    return _run_response(run)


@router.get("/dashboard")
def pivot_dashboard(
    as_of: date | None = Query(default=None),
    session: Session = Depends(get_db),
) -> dict:
    payload = build_pivot_dashboard(session, as_of=as_of)
    payload["approval_workflow"] = approval_workflow_enabled()
    return payload


@router.get("/selection")
def get_pivot_selection(
    request: Request,
    session: Session = Depends(get_db),
    read_context: ReadContext = Depends(read_context_from_query),
) -> dict:
    portfolio_symbols = [
        r.symbol
        for r in session.scalars(
            select(PivotPortfolioSymbol).order_by(
                PivotPortfolioSymbol.sort_order, PivotPortfolioSymbol.symbol
            )
        ).all()
    ]
    ctx = read_context if approval_workflow_enabled() else None
    return resolve_selection(
        session, ctx, fallback_portfolio_symbols=portfolio_symbols
    )


@router.put("/selection")
def put_pivot_selection(
    body: SelectionReplaceRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> dict:
    user = _user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    base_v = selection_row_version(session)
    if approval_workflow_enabled():
        try:
            draft = upsert_pivot_selection_draft(
                session,
                proposer=user,
                symbols=body.symbols,
                base_row_version=base_v,
            )
            session.commit()
        except ApprovalError as exc:
            session.rollback()
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        return {
            "symbols": body.symbols,
            "status": draft.status,
            "change_request_id": str(draft.change_request_id),
        }
    replace_official_selection(
        session,
        body.symbols,
        base_row_version=base_v,
        updated_by=user.user_id,
    )
    session.commit()
    return {"symbols": body.symbols, "status": "applied"}


@router.post("/selection/submit")
def submit_pivot_selection(
    request: Request,
    session: Session = Depends(get_db),
) -> dict:
    if not approval_workflow_enabled():
        raise HTTPException(status_code=400, detail="Approval workflow disabled")
    user = _user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    from pms_platform.approval.service import get_user_draft

    draft = get_user_draft(session, user_id=user.user_id, domain="pivot")
    if draft is None:
        raise HTTPException(status_code=404, detail="No draft change request")
    try:
        req = submit_request(session, actor=user, change_request_id=draft.change_request_id)
        session.commit()
    except ApprovalError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"change_request_id": str(req.change_request_id), "status": req.status}


@router.get("/portfolio")
def list_portfolio(session: Session = Depends(get_db)) -> list[dict]:
    rows = session.scalars(
        select(PivotPortfolioSymbol).order_by(
            PivotPortfolioSymbol.sort_order,
            PivotPortfolioSymbol.symbol,
        )
    ).all()
    return [
        {
            "symbol": r.symbol,
            "dummy": r.dummy,
            "portfolio_a": r.portfolio_a,
            "uptrend": r.uptrend,
            "support_note": r.support_note,
            "buy_note": r.buy_note,
            "sma_50": r.sma_50,
            "sma_100": r.sma_100,
            "sma_200": r.sma_200,
            "notes": r.notes,
        }
        for r in rows
    ]


@router.get("/symbols/search")
def search_symbols(
    q: str = Query(min_length=2, max_length=32),
    limit: int = Query(default=20, ge=1, le=50),
    session: Session = Depends(get_db),
) -> dict:
    return {"query": q.strip().upper(), "symbols": search_bhav_symbols(session, q, limit=limit)}


@router.put("/portfolio")
def replace_portfolio(
    body: PortfolioReplaceRequest,
    session: Session = Depends(get_db),
) -> dict:
    n = upsert_portfolio_symbols(session, [m.model_dump() for m in body.members])
    session.commit()
    return {"upserted": n}


@router.post("/portfolio/symbols")
def add_portfolio_symbol(
    body: AddFirmRequest,
    session: Session = Depends(get_db),
) -> dict:
    """Add one selected firm; symbol must exist in stored bhav EQ/BE."""
    symbol = body.symbol.strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="Symbol is required")
    if symbol in HIDDEN_PIVOT_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"{symbol} is not shown on Pivot")
    known = known_bhav_symbols(session)
    if not known:
        raise HTTPException(
            status_code=400,
            detail="No bhav data loaded yet — commit a bhav day before adding firms",
        )
    if symbol not in known:
        raise HTTPException(
            status_code=400,
            detail=f"{symbol} is not a known NSE EQ/BE symbol in bhav data",
        )
    n = upsert_portfolio_symbols(session, [{"symbol": symbol}])
    session.commit()
    return {"symbol": symbol, "upserted": n}


@router.delete("/portfolio/symbols/{symbol}")
def remove_portfolio_symbol(
    symbol: str,
    session: Session = Depends(get_db),
) -> dict:
    key = symbol.strip().upper()
    if not delete_portfolio_symbol(session, key):
        raise HTTPException(status_code=404, detail=f"{key} is not in selected firms")
    session.commit()
    return {"deleted": key}
