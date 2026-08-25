"""Client Portfolio strategy dashboard API."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from pms_platform.api.routes.episodes import get_db
from pms_platform.market_data.client_portfolio_dashboard import (
    build_client_portfolio_dashboard,
)
from pms_platform.market_data.client_portfolio_parse import write_bse_smallcap_year
from pms_platform.market_data.daily_edit_bhav import write_sca_bank_balance

router = APIRouter()


@router.get("/dashboard")
def client_portfolio_dashboard(
    as_of: date | None = Query(default=None),
    book: str = Query(default="client"),
    session: Session = Depends(get_db),
) -> dict:
    return build_client_portfolio_dashboard(session, as_of=as_of, book=book)


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
