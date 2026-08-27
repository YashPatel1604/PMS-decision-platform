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
from pms_platform.domain.client_positions import (
    holdings_domain,
    official_qty_map,
    set_bank_balance,
    update_position_fields,
)
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
    book_key = book.strip().lower()
    if approval_workflow_enabled() and book_key in ("client", "sca"):
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
    book: str = Query(default="client"),
    session: Session = Depends(get_db),
) -> dict:
    if not approval_workflow_enabled():
        raise HTTPException(status_code=400, detail="Approval workflow disabled")
    user = _user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    domain = holdings_domain(book)
    draft = get_user_draft(session, user_id=user.user_id, domain=domain)
    if draft is None:
        raise HTTPException(status_code=404, detail="No draft change request")
    try:
        req = submit_request(session, actor=user, change_request_id=draft.change_request_id)
        session.commit()
    except ApprovalError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"change_request_id": str(req.change_request_id), "status": req.status}


@router.patch("/positions/{symbol}/fields")
def patch_position_fields(
    symbol: str,
    request: Request,
    body: dict = Body(...),
    book: str = Query(default="client"),
    session: Session = Depends(get_db),
) -> dict:
    if not approval_workflow_enabled():
        raise HTTPException(
            status_code=400,
            detail="Approval workflow disabled — edit index/mcap in Excel or enable FEATURE_APPROVAL_WORKFLOW",
        )
    if (book or "").strip().lower() != "client":
        raise HTTPException(status_code=400, detail="Index/mcap fields apply to client book only")
    user = _user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    sym = symbol.strip().upper()
    touch_index = "index_label" in body
    touch_mcap = "mcap_factor" in body
    if not touch_index and not touch_mcap:
        raise HTTPException(status_code=400, detail="Provide index_label and/or mcap_factor")
    index_label = body.get("index_label")
    mcap_raw = body.get("mcap_factor")
    mcap_factor = None
    if touch_mcap:
        if mcap_raw is None:
            mcap_factor = None
        else:
            try:
                mcap_factor = Decimal(str(mcap_raw))
            except (InvalidOperation, ValueError) as exc:
                raise HTTPException(status_code=400, detail="mcap_factor must be a number") from exc
    try:
        pos = update_position_fields(
            session,
            symbol=sym,
            book="client",
            updated_by=user.user_id,
            index_label=str(index_label).strip() if index_label else None,
            mcap_factor=mcap_factor,
            touch_index=touch_index,
            touch_mcap_factor=touch_mcap,
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "symbol": sym,
        "index_label": pos.index_label,
        "mcap_factor": float(pos.mcap_factor) if pos.mcap_factor is not None else None,
        "row_version": pos.row_version,
    }


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
    request: Request,
    amount: float = Body(..., embed=True),
    book: str = Query(default="sca"),
    session: Session = Depends(get_db),
) -> dict:
    if (book or "").strip().lower() != "sca":
        raise HTTPException(status_code=400, detail="Balance with Bank is only on SCA LLP.")
    try:
        value = Decimal(str(amount))
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(status_code=400, detail="amount must be a number") from exc
    if approval_workflow_enabled():
        user = _user(request)
        if user is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        written = set_bank_balance(
            session, book="sca", amount=value, updated_by=user.user_id
        )
        session.commit()
        return {"bank_balance": float(written)}
    try:
        written = write_sca_bank_balance(value)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"bank_balance": written}
