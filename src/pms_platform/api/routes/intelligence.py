"""Morning brief, theses, and surveillance event APIs."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from pms_platform.api.deps import get_current_user, get_db
from pms_platform.intelligence.brief import build_morning_brief
from pms_platform.intelligence.conflicts import (
    create_conflict_flag,
    list_conflict_flags,
    update_conflict_flag,
)
from pms_platform.intelligence.events import list_events, sync_insider_events, upsert_event
from pms_platform.intelligence.theses import create_thesis, list_theses, revise_thesis
from pms_platform.models.user import User

router = APIRouter()


class ThesisBody(BaseModel):
    security_id: str
    status: str = "active"
    thesis_summary: str | None = None
    business_quality: str | None = None
    industry_thesis: str | None = None
    competitive_advantage: str | None = None
    management_thesis: str | None = None
    capital_allocation_thesis: str | None = None
    revenue_assumption: str | None = None
    margin_assumption: str | None = None
    earnings_assumption: str | None = None
    valuation_framework: str | None = None
    expected_holding_period: str | None = None
    bull_case: str | None = None
    base_case: str | None = None
    bear_case: str | None = None
    key_risks: str | None = None
    key_monitoring_variables: str | None = None
    disconfirming_evidence: str | None = None


class ThesisReviseBody(BaseModel):
    thesis_summary: str | None = None
    business_quality: str | None = None
    industry_thesis: str | None = None
    competitive_advantage: str | None = None
    management_thesis: str | None = None
    capital_allocation_thesis: str | None = None
    revenue_assumption: str | None = None
    margin_assumption: str | None = None
    earnings_assumption: str | None = None
    valuation_framework: str | None = None
    expected_holding_period: str | None = None
    bull_case: str | None = None
    base_case: str | None = None
    bear_case: str | None = None
    key_risks: str | None = None
    key_monitoring_variables: str | None = None
    disconfirming_evidence: str | None = None


class EventCreateBody(BaseModel):
    event_type: str
    summary: str = Field(min_length=1)
    materiality: str
    materiality_reason: str = Field(min_length=1)
    source: str = "manual"
    security_id: str | None = None
    company: str | None = None
    event_date: date | None = None
    source_url: str | None = None
    raw_document_reference: str | None = None
    affected_thesis: str | None = None
    dedupe_key: str | None = None


class ConflictBody(BaseModel):
    thesis_id: int
    security_id: str
    assumption_affected: str
    what_changed: str
    severity: str
    evidence: str
    event_id: int | None = None
    management_explanation: str | None = None
    investigate_next: str | None = None


def _thesis_dict(row: Any) -> dict[str, Any]:
    return {
        "thesis_id": row.thesis_id,
        "security_id": row.security_id,
        "version": row.version,
        "status": row.status,
        "thesis_summary": row.thesis_summary,
        "business_quality": row.business_quality,
        "industry_thesis": row.industry_thesis,
        "competitive_advantage": row.competitive_advantage,
        "management_thesis": row.management_thesis,
        "capital_allocation_thesis": row.capital_allocation_thesis,
        "revenue_assumption": row.revenue_assumption,
        "margin_assumption": row.margin_assumption,
        "earnings_assumption": row.earnings_assumption,
        "valuation_framework": row.valuation_framework,
        "expected_holding_period": row.expected_holding_period,
        "bull_case": row.bull_case,
        "base_case": row.base_case,
        "bear_case": row.bear_case,
        "key_risks": row.key_risks,
        "key_monitoring_variables": row.key_monitoring_variables,
        "disconfirming_evidence": row.disconfirming_evidence,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


@router.get("/brief")
def get_brief(
    lookback_days: int = Query(default=7, ge=1, le=60),
    session: Session = Depends(get_db),
    _user: User | None = Depends(get_current_user),
) -> dict[str, object]:
    return build_morning_brief(session, lookback_days=lookback_days)


@router.post("/events/sync-insider")
def post_sync_insider(
    days: int = Query(default=14, ge=1, le=90),
    session: Session = Depends(get_db),
    _user: User | None = Depends(get_current_user),
) -> dict[str, int]:
    return sync_insider_events(session, days=days)


@router.get("/events")
def get_events(
    since: date | None = None,
    universe: str | None = None,
    materiality: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_db),
    _user: User | None = Depends(get_current_user),
) -> list[dict[str, object]]:
    mats = {m.strip().upper() for m in materiality.split(",")} if materiality else None
    rows = list_events(session, since=since, materialities=mats, universe=universe, limit=limit)
    return [
        {
            "event_id": r.event_id,
            "security_id": r.security_id,
            "company": r.company,
            "event_type": r.event_type,
            "event_date": r.event_date.isoformat() if r.event_date else None,
            "source": r.source,
            "summary": r.summary,
            "materiality": r.materiality,
            "materiality_reason": r.materiality_reason,
            "universe": r.universe,
            "raw_document_reference": r.raw_document_reference,
        }
        for r in rows
    ]


@router.post("/events", status_code=201)
def post_event(
    body: EventCreateBody,
    session: Session = Depends(get_db),
    _user: User | None = Depends(get_current_user),
) -> dict[str, object]:
    import hashlib

    key = body.dedupe_key or hashlib.sha256(
        f"manual|{body.security_id}|{body.event_type}|{body.summary}".encode()
    ).hexdigest()[:64]
    try:
        row = upsert_event(
            session,
            dedupe_key=key,
            event_type=body.event_type,
            summary=body.summary,
            materiality=body.materiality,
            materiality_reason=body.materiality_reason,
            source=body.source,
            security_id=body.security_id,
            company=body.company,
            event_date=body.event_date,
            source_url=body.source_url,
            raw_document_reference=body.raw_document_reference,
            affected_thesis=body.affected_thesis,
            confidence="human",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "event_id": row.event_id,
        "dedupe_key": row.dedupe_key,
        "materiality": row.materiality,
        "universe": row.universe,
    }


@router.get("/theses")
def get_theses(
    security_id: str | None = None,
    active_only: bool = True,
    session: Session = Depends(get_db),
    _user: User | None = Depends(get_current_user),
) -> list[dict[str, Any]]:
    return [_thesis_dict(t) for t in list_theses(session, security_id=security_id, active_only=active_only)]


@router.post("/theses", status_code=201)
def post_thesis(
    body: ThesisBody,
    session: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
) -> dict[str, Any]:
    data = body.model_dump()
    security_id = data.pop("security_id")
    status = data.pop("status")
    try:
        row = create_thesis(
            session,
            security_id=security_id,
            status=status,
            created_by=user.email if user else None,
            **data,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _thesis_dict(row)


@router.post("/theses/{thesis_id}/revise", status_code=201)
def post_revise_thesis(
    thesis_id: int,
    body: ThesisReviseBody,
    session: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        row = revise_thesis(
            session,
            thesis_id,
            created_by=user.email if user else None,
            **{k: v for k, v in body.model_dump().items() if v is not None},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _thesis_dict(row)


@router.get("/conflicts")
def get_conflicts(
    security_id: str | None = None,
    open_only: bool = True,
    session: Session = Depends(get_db),
    _user: User | None = Depends(get_current_user),
) -> list[dict[str, Any]]:
    rows = list_conflict_flags(session, security_id=security_id, open_only=open_only)
    return [
        {
            "flag_id": r.flag_id,
            "thesis_id": r.thesis_id,
            "security_id": r.security_id,
            "event_id": r.event_id,
            "assumption_affected": r.assumption_affected,
            "what_changed": r.what_changed,
            "severity": r.severity,
            "evidence": r.evidence,
            "status": r.status,
            "investigate_next": r.investigate_next,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.post("/conflicts", status_code=201)
def post_conflict(
    body: ConflictBody,
    session: Session = Depends(get_db),
    _user: User | None = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        row = create_conflict_flag(session, **body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"flag_id": row.flag_id, "status": row.status}


@router.patch("/conflicts/{flag_id}")
def patch_conflict(
    flag_id: int,
    status: str = Query(...),
    session: Session = Depends(get_db),
    _user: User | None = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        row = update_conflict_flag(session, flag_id, status=status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Conflict flag not found")
    return {"flag_id": row.flag_id, "status": row.status}
