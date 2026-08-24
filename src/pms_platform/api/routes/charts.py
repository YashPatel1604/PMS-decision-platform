"""Charts Range strategy dashboard API."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from pms_platform.api.routes.episodes import get_db
from pms_platform.market_data.charts_dashboard import (
    build_charts_dashboard,
    write_charts_range_weekly,
)

router = APIRouter()


@router.get("/dashboard")
def charts_dashboard(
    as_of: date | None = Query(default=None),
    session: Session = Depends(get_db),
) -> dict:
    return build_charts_dashboard(session, as_of=as_of)


@router.patch("/weekly")
def patch_charts_weekly(
    excel_row: int = Body(...),
    weekly_close: float | None = Body(default=None),
    support_resistance: str | None = Body(default=None),
    weekly_close_date: str | None = Body(default=None),
) -> dict:
    try:
        return write_charts_range_weekly(
            excel_row,
            weekly_close=weekly_close,
            support_resistance=support_resistance,
            weekly_close_date=weekly_close_date,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
