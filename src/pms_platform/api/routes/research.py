"""Research index + analyst API routes."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from pms_platform.api.deps import get_current_user, get_db
from pms_platform.documents.analyst import generate_research_ask, generate_research_brief
from pms_platform.documents.coverage import run_coverage_briefs, securities_needing_coverage
from pms_platform.documents.goals import create_goal, list_goals, update_goal
from pms_platform.documents.indexer import index_research_corpus, index_status
from pms_platform.documents.search import search_research_pages
from pms_platform.documents.xai_client import XaiConfigError
from pms_platform.models.user import User

router = APIRouter()


class IndexResponse(BaseModel):
    root: str | None
    scanned: int
    inserted: int
    updated: int
    unchanged: int
    skipped: int
    errors: int
    removed: int


class SearchHitResponse(BaseModel):
    page_id: int
    document_id: int
    relative_path: str
    page_number: int
    title: str | None
    security_id: str | None
    snippet: str
    rank: float


class BriefRequest(BaseModel):
    security_id: str | None = None
    query_name: str | None = None
    extra_question: str | None = None
    as_of: date | None = None
    force_refresh: bool = False


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    security_id: str | None = None
    as_of: date | None = None
    force_refresh: bool = False


class AnalystResponse(BaseModel):
    kind: str
    response: dict[str, Any]
    cache_hit: bool
    cache_id: int | None
    model: str | None
    token_in: int | None
    token_out: int | None
    chunk_ids: list[int]
    called_llm: bool


class GoalResponse(BaseModel):
    goal_id: int
    security_id: str
    title: str
    rationale: str | None
    priority: int
    status: str
    source_cache_id: int | None
    created_by_user: str | None
    created_at: str
    updated_at: str


class GoalCreateRequest(BaseModel):
    security_id: str
    title: str = Field(min_length=1)
    rationale: str | None = None
    priority: int = 0
    status: str = "accepted"
    source_cache_id: int | None = None


class GoalUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    rationale: str | None = None
    priority: int | None = None
    status: str | None = None


def _goal_response(goal: Any) -> GoalResponse:
    return GoalResponse(
        goal_id=goal.goal_id,
        security_id=goal.security_id,
        title=goal.title,
        rationale=goal.rationale,
        priority=goal.priority,
        status=goal.status,
        source_cache_id=goal.source_cache_id,
        created_by_user=goal.created_by_user,
        created_at=goal.created_at.isoformat(),
        updated_at=goal.updated_at.isoformat(),
    )


@router.post("/index", response_model=IndexResponse)
def post_index(
    session: Session = Depends(get_db),
    _user: User | None = Depends(get_current_user),
) -> IndexResponse:
    result = index_research_corpus(session)
    return IndexResponse(**asdict(result))


@router.get("/status")
def get_status(
    session: Session = Depends(get_db),
    _user: User | None = Depends(get_current_user),
) -> dict[str, object]:
    return index_status(session)


@router.get("/search", response_model=list[SearchHitResponse])
def get_search(
    q: str = Query(min_length=1),
    security_id: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    as_of: date | None = None,
    session: Session = Depends(get_db),
    _user: User | None = Depends(get_current_user),
) -> list[SearchHitResponse]:
    hits = search_research_pages(session, q, security_id=security_id, limit=limit, as_of=as_of)
    return [
        SearchHitResponse(
            page_id=hit.page_id,
            document_id=hit.document_id,
            relative_path=hit.relative_path,
            page_number=hit.page_number,
            title=hit.title,
            security_id=hit.security_id,
            snippet=hit.snippet,
            rank=hit.rank,
        )
        for hit in hits
    ]


@router.post("/brief", response_model=AnalystResponse)
def post_brief(
    body: BriefRequest,
    session: Session = Depends(get_db),
    _user: User | None = Depends(get_current_user),
) -> AnalystResponse:
    if not body.security_id and not body.query_name:
        raise HTTPException(status_code=400, detail="security_id or query_name required")
    try:
        result = generate_research_brief(
            session,
            security_id=body.security_id,
            query_name=body.query_name,
            extra_question=body.extra_question,
            as_of=body.as_of,
            force_refresh=body.force_refresh,
        )
    except XaiConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return AnalystResponse(
        kind=result.kind,
        response=result.response,
        cache_hit=result.cache_hit,
        cache_id=result.cache_id,
        model=result.model,
        token_in=result.token_in,
        token_out=result.token_out,
        chunk_ids=result.chunk_ids,
        called_llm=result.called_llm,
    )


@router.post("/ask", response_model=AnalystResponse)
def post_ask(
    body: AskRequest,
    session: Session = Depends(get_db),
    _user: User | None = Depends(get_current_user),
) -> AnalystResponse:
    try:
        result = generate_research_ask(
            session,
            question=body.question,
            security_id=body.security_id,
            as_of=body.as_of,
            force_refresh=body.force_refresh,
        )
    except XaiConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AnalystResponse(
        kind=result.kind,
        response=result.response,
        cache_hit=result.cache_hit,
        cache_id=result.cache_id,
        model=result.model,
        token_in=result.token_in,
        token_out=result.token_out,
        chunk_ids=result.chunk_ids,
        called_llm=result.called_llm,
    )


@router.get("/goals", response_model=list[GoalResponse])
def get_goals(
    security_id: str | None = None,
    include_dismissed: bool = False,
    session: Session = Depends(get_db),
    _user: User | None = Depends(get_current_user),
) -> list[GoalResponse]:
    goals = list_goals(session, security_id=security_id, include_dismissed=include_dismissed)
    return [_goal_response(g) for g in goals]


@router.post("/goals", response_model=GoalResponse, status_code=201)
def post_goal(
    body: GoalCreateRequest,
    session: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
) -> GoalResponse:
    created_by = user.email if user is not None else None
    goal = create_goal(
        session,
        security_id=body.security_id,
        title=body.title,
        rationale=body.rationale,
        priority=body.priority,
        status=body.status,
        source_cache_id=body.source_cache_id,
        created_by_user=created_by,
    )
    return _goal_response(goal)


@router.patch("/goals/{goal_id}", response_model=GoalResponse)
def patch_goal(
    goal_id: int,
    body: GoalUpdateRequest,
    session: Session = Depends(get_db),
    _user: User | None = Depends(get_current_user),
) -> GoalResponse:
    goal = update_goal(
        session,
        goal_id,
        title=body.title,
        rationale=body.rationale,
        priority=body.priority,
        status=body.status,
    )
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return _goal_response(goal)


@router.get("/coverage")
def get_coverage(
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_db),
    _user: User | None = Depends(get_current_user),
) -> list[dict[str, str]]:
    items = securities_needing_coverage(session, limit=limit)
    return [{"security_id": i.security_id, "reason": i.reason} for i in items]


@router.post("/coverage/run")
def post_coverage_run(
    limit: int = Query(default=10, ge=1, le=50),
    dry_run: bool = True,
    session: Session = Depends(get_db),
    _user: User | None = Depends(get_current_user),
) -> list[dict[str, object]]:
    try:
        return run_coverage_briefs(session, limit=limit, dry_run=dry_run)
    except XaiConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
