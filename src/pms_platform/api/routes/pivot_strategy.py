"""Pivot Point Strategy: bhav upload loop + dashboard API."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from pms_platform.api.routes.episodes import get_db
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
    return build_pivot_dashboard(session, as_of=as_of)


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
