"""Charts Range strategy dashboard API."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from pms_platform.api.deps import get_db
from pms_platform.domain.charts_rows import apply_row_patch
from pms_platform.feature_flags import approval_workflow_enabled
from pms_platform.market_data.charts_dashboard import (
    build_charts_dashboard,
    write_charts_range_hlc,
    write_charts_range_weekly,
)
from pms_platform.models.user import User

router = APIRouter()


def _user(request: Request) -> User | None:
    return getattr(request.state, "user", None)


@router.get("/dashboard")
def charts_dashboard(
    as_of: date | None = Query(default=None),
    session: Session = Depends(get_db),
) -> dict:
    result = build_charts_dashboard(session, as_of=as_of)
    if approval_workflow_enabled():
        session.commit()
    return result


@router.patch("/levels")
def patch_charts_levels(
    request: Request,
    excel_row: int = Body(...),
    high: float | None = Body(default=None),
    low: float | None = Body(default=None),
    close: float | None = Body(default=None),
    session: Session = Depends(get_db),
) -> dict:
    if high is None and low is None and close is None:
        raise HTTPException(status_code=400, detail="Provide high, low, and/or close")
    if approval_workflow_enabled():
        user = _user(request)
        patch: dict[str, float | None] = {}
        if high is not None:
            patch["high"] = high
        if low is not None:
            patch["low"] = low
        if close is not None:
            patch["close"] = close
        try:
            row = apply_row_patch(
                session,
                excel_row=excel_row,
                patch=patch,
                updated_by=user.user_id if user else None,
            )
            session.commit()
        except ValueError as exc:
            session.rollback()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "excel_row": excel_row,
            "high": float(row.high) if row.high is not None else None,
            "low": float(row.low) if row.low is not None else None,
            "close": float(row.close_override) if row.close_override is not None else None,
        }
    try:
        return write_charts_range_hlc(excel_row, high=high, low=low, close=close)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/weekly")
def patch_charts_weekly(
    request: Request,
    excel_row: int = Body(...),
    weekly_close: float | None = Body(default=None),
    support_resistance: str | None = Body(default=None),
    weekly_close_date: str | None = Body(default=None),
    session: Session = Depends(get_db),
) -> dict:
    if approval_workflow_enabled():
        user = _user(request)
        patch: dict[str, float | str | None] = {}
        if weekly_close is not None:
            patch["weekly_close"] = weekly_close
        if support_resistance is not None:
            patch["support_resistance"] = support_resistance
        if weekly_close_date is not None:
            patch["weekly_close_date"] = weekly_close_date
        if not patch:
            raise HTTPException(status_code=400, detail="Provide weekly fields to update")
        try:
            row = apply_row_patch(
                session,
                excel_row=excel_row,
                patch=patch,
                updated_by=user.user_id if user else None,
            )
            session.commit()
        except ValueError as exc:
            session.rollback()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "excel_row": excel_row,
            "weekly_close": float(row.weekly_close) if row.weekly_close is not None else None,
            "support_resistance": row.support_resistance,
            "weekly_close_date": row.weekly_close_date,
        }
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
