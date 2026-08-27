"""Client Portfolio strategy dashboard API."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from pms_platform.api.deps import get_db
from pms_platform.api.deps_read_context import read_context_from_query
from pms_platform.approval.service import (
    ApprovalError,
    get_user_draft,
    submit_request,
    upsert_client_position_qty_draft,
)
from pms_platform.domain.client_positions import official_qty_map
from pms_platform.feature_flags import approval_workflow_enabled
from pms_platform.market_data.client_portfolio_dashboard import (
    build_client_portfolio_dashboard,
)
from pms_platform.market_data.client_portfolio_parse import write_bse_smallcap_year
from pms_platform.market_data.daily_edit_bhav import write_sca_bank_balance
from pms_platform.models.user import User
from pms_platform.read_context import ReadContext

router = APIRouter()


def _user(request: Request) -> User | None:
    return getattr(request.state, "user", None)


@router.get("/dashboard")
def client_portfolio_dashboard(
    as_of: date | None = Query(default=None),
    book: str = Query(default="client"),
    session: Session = Depends(get_db),
    read_context: ReadContext = Depends(read_context_from_query),
) -> dict:
    ctx = None
    if approval_workflow_enabled() and book.strip().lower() == "client":
        ctx = read_context
    return build_client_portfolio_dashboard(
        session, as_of=as_of, book=book, read_context=ctx
    )


@router.patch("/positions/{symbol}/qty")
def patch_position_qty(
    symbol: str,
    request: Request,
    qty: float = Body(..., embed=True),
    book: str = Query(default="client"),
    session: Session = Depends(get_db),
) -> dict:
    if not approval_workflow_enabled():
        raise HTTPException(
            status_code=400,
            detail="Approval workflow disabled — edit qty in Excel or enable FEATURE_APPROVAL_WORKFLOW",
        )
    user = _user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    sym = symbol.strip().upper()
    book_key = book.strip().lower()
    try:
        qty_d = Decimal(str(qty))
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(status_code=400, detail="qty must be a number") from exc
    official = official_qty_map(session, book=book_key).get(sym)
    base_v = official.row_version if official is not None else 1
    try:
        draft = upsert_client_position_qty_draft(
            session,
            proposer=user,
            symbol=sym,
            qty=qty_d,
            base_row_version=base_v,
            book=book_key,
        )
        session.commit()
    except ApprovalError as exc:
        session.rollback()
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {
        "symbol": sym,
        "proposed_qty": float(qty_d),
        "change_request_id": str(draft.change_request_id),
        "status": draft.status,
    }


@router.post("/positions/{symbol}/submit")
def submit_position_qty_change(
    symbol: str,
    request: Request,
    session: Session = Depends(get_db),
) -> dict:
    if not approval_workflow_enabled():
        raise HTTPException(status_code=400, detail="Approval workflow disabled")
    user = _user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    draft = get_user_draft(session, user_id=user.user_id, domain="client_portfolio")
    if draft is None:
        raise HTTPException(status_code=404, detail="No draft change request")
    try:
        req = submit_request(session, actor=user, change_request_id=draft.change_request_id)
        session.commit()
    except ApprovalError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"change_request_id": str(req.change_request_id), "status": req.status}


@router.patch("/bse-smallcap-year")
def patch_bse_smallcap_year(
    year: int = Body(...),
    start: float | None = Body(default=None),
    end: float | None = Body(default=None),
) -> dict:
    if start is None and end is None:
        raise HTTPException(status_code=400, detail="Provide start and/or end")
    try:
        start_d = Decimal(str(start)) if start is not None else None
        end_d = Decimal(str(end)) if end is not None else None
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(status_code=400, detail="start/end must be numbers") from exc
    try:
        return write_bse_smallcap_year(year=year, start=start_d, end=end_d)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=409,
            detail="Workbook is locked or read-only. Close Excel and retry.",
        ) from exc
    except OSError as exc:
        raise HTTPException(status_code=503, detail=f"Could not save workbook: {exc}") from exc


@router.patch("/bank-balance")
def patch_bank_balance(
    amount: float = Body(..., embed=True),
    book: str = Query(default="sca"),
) -> dict:
    if (book or "").strip().lower() != "sca":
        raise HTTPException(status_code=400, detail="Balance with Bank is only on SCA LLP.")
    try:
        value = Decimal(str(amount))
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(status_code=400, detail="amount must be a number") from exc
    try:
        written = write_sca_bank_balance(value)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"bank_balance": written}
