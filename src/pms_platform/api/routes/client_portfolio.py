"""Client Portfolio strategy dashboard API."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from pms_platform.api.routes.episodes import get_db
from pms_platform.market_data.client_portfolio_dashboard import (
    build_client_portfolio_dashboard,
)

router = APIRouter()


@router.get("/dashboard")
def client_portfolio_dashboard(
    as_of: date | None = Query(default=None),
    session: Session = Depends(get_db),
) -> dict:
    return build_client_portfolio_dashboard(session, as_of=as_of)
