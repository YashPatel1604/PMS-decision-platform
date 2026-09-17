"""Watchlist REST API."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from pms_platform.api.deps import get_db
from pms_platform.documents.coverage import research_status_by_security
from pms_platform.fundamentals.catalog import FUNDAMENTALS_PROVIDERS, validated_fundamentals_provider
from pms_platform.models.watchlist import Watchlist, WatchlistAlert, WatchlistMember
from pms_platform.watchlists import alerts as wa
from pms_platform.watchlists import export_import as wi
from pms_platform.watchlists import health as wh
from pms_platform.watchlists import refresh as wr
from pms_platform.watchlists import resolution as res
from pms_platform.watchlists import screen as scr
from pms_platform.watchlists import service as wl

router = APIRouter()


class WatchlistResponse(BaseModel):
    watchlist_id: int
    name: str
    description: str | None
    is_default: bool
    member_count: int
    created_at: datetime
    updated_at: datetime


class WatchlistCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    make_default: bool = False


class WatchlistUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    make_default: bool | None = None


class WatchlistMemberResponse(BaseModel):
    member_id: int
    watchlist_id: int
    security_id: str | None
    display_name: str
    nse_symbol: str | None
    bse_code: str | None
    isin: str | None
    notes: str | None
    resolution_status: str
    resolution_source: str | None = None
    resolution_note: str | None = None
    resolved_at: datetime | None = None
    resolution_stale: bool = False
    sector: str | None = None
    industry: str | None = None
    in_portfolio: bool = False
    research_status: str = "unlinked"
    added_at: datetime


class WatchlistMemberCreateRequest(BaseModel):
    portfolio_name: str | None = None
    security_id: str | None = None
    nse_symbol: str | None = None
    bse_code: str | None = None
    display_name: str | None = None
    notes: str | None = None


class WatchlistBulkMembersRequest(BaseModel):
    text: str = Field(min_length=1)


class WatchlistBulkMembersResponse(BaseModel):
    added: int
    skipped: int
    pending: int


class WatchlistMemberUpdateRequest(BaseModel):
    display_name: str | None = None
    nse_symbol: str | None = None
    bse_code: str | None = None
    notes: str | None = None


class SecuritySearchHitResponse(BaseModel):
    source: str
    security_id: str | None
    portfolio_name: str
    nse_symbol: str | None
    bse_code: str | None
    isin: str | None
    sector: str | None
    industry: str | None
    yahoo_ticker: str | None = None


class ResolveWatchlistResponse(BaseModel):
    resolved: int
    failed: int
    skipped: int


class MetricDefinitionResponse(BaseModel):
    key: str
    label: str
    group: str
    format: str
    description: str


class WatchlistScreenRowResponse(BaseModel):
    member_id: int
    display_name: str
    nse_symbol: str | None
    bse_code: str | None
    security_id: str | None
    sector: str | None
    industry: str | None
    resolution_status: str
    fiscal_year: int | None
    fiscal_quarter: str | None
    period_end_date: str | None
    retrieved_at: datetime | None
    has_fundamentals: bool
    fundamentals_stale: bool
    metrics: dict[str, float | None]


class WatchlistScreenResponse(BaseModel):
    watchlist_id: int
    columns: list[str]
    sort: str | None
    row_count: int
    rows: list[WatchlistScreenRowResponse]


class WatchlistAlertResponse(BaseModel):
    alert_id: int
    watchlist_id: int
    member_id: int | None
    kind: str
    disclosure_date: str
    bse_code: str
    company_name: str
    person_name: str
    category: str
    transaction_type: str
    quantity: float | None
    value: float | None
    pct_pre: float | None
    pct_post: float | None
    mode: str
    regulation: str
    market_cap_cr: float | None
    fetched_at: datetime
    acknowledged: bool
    acknowledged_at: datetime | None
    created_at: datetime


class AlertPollResponse(BaseModel):
    inserted: int
    skipped: int
    matched: int


class AlertSummaryResponse(BaseModel):
    unacknowledged: int


class ResolutionRefreshStatsResponse(BaseModel):
    resolved: int
    failed: int
    skipped: int


class FundamentalsRefreshStatsResponse(BaseModel):
    csv_inserted: int
    csv_updated: int
    csv_skipped: int
    csv_invalid: int
    snapshots_written: int
    identifiers_processed: int


class AlertsRefreshStatsResponse(BaseModel):
    inserted: int
    skipped: int
    matched: int


class WatchlistRefreshResponse(BaseModel):
    watchlist_id: int
    watchlist_name: str
    resolution: ResolutionRefreshStatsResponse
    fundamentals: FundamentalsRefreshStatsResponse | None
    alerts: AlertsRefreshStatsResponse
    duration_ms: int


class SyncWatchlistsResponse(BaseModel):
    watchlists_refreshed: int
    fundamentals: FundamentalsRefreshStatsResponse | None
    results: list[WatchlistRefreshResponse]


class WatchlistSettingsResponse(BaseModel):
    fundamentals_provider: str
    available_providers: list[str]


class WatchlistHealthRowResponse(BaseModel):
    watchlist_id: int
    name: str
    member_count: int
    resolved_count: int
    unresolved_count: int
    stale_resolution_count: int
    with_fundamentals_count: int
    missing_fundamentals_count: int
    stale_fundamentals_count: int
    unacknowledged_alerts: int
    refresh_locked: bool


class WatchlistsHealthResponse(BaseModel):
    fundamentals_provider: str
    watchlist_count: int
    total_members: int
    total_unresolved: int
    total_stale_resolution: int
    total_missing_fundamentals: int
    total_stale_fundamentals: int
    total_unacknowledged_alerts: int
    any_refresh_locked: bool
    watchlists: list[WatchlistHealthRowResponse]


class WatchlistImportRequest(BaseModel):
    payload: dict
    watchlist_id: int | None = None
    create_name: str | None = None


class WatchlistImportResponse(BaseModel):
    watchlist_id: int
    watchlist_name: str
    members_added: int
    members_skipped: int


def _refresh_response(result: wr.WatchlistRefreshResult) -> WatchlistRefreshResponse:
    fundamentals = None
    if result.fundamentals is not None:
        fundamentals = FundamentalsRefreshStatsResponse(
            csv_inserted=result.fundamentals.csv_inserted,
            csv_updated=result.fundamentals.csv_updated,
            csv_skipped=result.fundamentals.csv_skipped,
            csv_invalid=result.fundamentals.csv_invalid,
            snapshots_written=result.fundamentals.snapshots_written,
            identifiers_processed=result.fundamentals.identifiers_processed,
        )
    return WatchlistRefreshResponse(
        watchlist_id=result.watchlist_id,
        watchlist_name=result.watchlist_name,
        resolution=ResolutionRefreshStatsResponse(
            resolved=result.resolution.resolved,
            failed=result.resolution.failed,
            skipped=result.resolution.skipped,
        ),
        fundamentals=fundamentals,
        alerts=AlertsRefreshStatsResponse(
            inserted=result.alerts.inserted,
            skipped=result.alerts.skipped,
            matched=result.alerts.matched,
        ),
        duration_ms=result.duration_ms,
    )


def _alert_response(row: WatchlistAlert) -> WatchlistAlertResponse:
    return WatchlistAlertResponse(
        alert_id=row.alert_id,
        watchlist_id=row.watchlist_id,
        member_id=row.member_id,
        kind=row.kind,
        disclosure_date=row.disclosure_date.isoformat(),
        bse_code=row.bse_code,
        company_name=row.company_name,
        person_name=row.person_name,
        category=row.category,
        transaction_type=row.transaction_type,
        quantity=float(row.quantity) if row.quantity is not None else None,
        value=float(row.value) if row.value is not None else None,
        pct_pre=float(row.pct_pre) if row.pct_pre is not None else None,
        pct_post=float(row.pct_post) if row.pct_post is not None else None,
        mode=row.mode,
        regulation=row.regulation,
        market_cap_cr=float(row.market_cap_cr) if row.market_cap_cr is not None else None,
        fetched_at=row.fetched_at,
        acknowledged=row.acknowledged,
        acknowledged_at=row.acknowledged_at,
        created_at=row.created_at,
    )


def _watchlist_response(session: Session, row: Watchlist) -> WatchlistResponse:
    return WatchlistResponse(
        watchlist_id=row.watchlist_id,
        name=row.name,
        description=row.description,
        is_default=row.is_default,
        member_count=wl.member_count(session, row.watchlist_id),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _member_response(
    row: WatchlistMember, *, research_status: str = "unlinked"
) -> WatchlistMemberResponse:
    sec = row.security
    return WatchlistMemberResponse(
        member_id=row.member_id,
        watchlist_id=row.watchlist_id,
        security_id=row.security_id,
        display_name=row.display_name,
        nse_symbol=row.nse_symbol,
        bse_code=row.bse_code,
        isin=row.isin,
        notes=row.notes,
        resolution_status=row.resolution_status,
        resolution_source=row.resolution_source,
        resolution_note=row.resolution_note,
        resolved_at=row.resolved_at,
        resolution_stale=res.is_resolution_stale(row),
        sector=sec.sector if sec else None,
        industry=sec.industry if sec else None,
        in_portfolio=sec is not None,
        research_status=research_status,
        added_at=row.added_at,
    )


def _research_status_for_member(
    row: WatchlistMember, status_map: dict[str, str]
) -> str:
    if not row.security_id:
        return "unlinked"
    return status_map.get(row.security_id, "backlog")


@router.get("", response_model=list[WatchlistResponse])
def list_watchlists(session: Session = Depends(get_db)) -> list[WatchlistResponse]:
    rows = wl.list_watchlists(session)
    counts = wl.member_counts(session)
    return [
        WatchlistResponse(
            watchlist_id=row.watchlist_id,
            name=row.name,
            description=row.description,
            is_default=row.is_default,
            member_count=counts.get(row.watchlist_id, 0),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@router.post("", response_model=WatchlistResponse, status_code=201)
def create_watchlist(
    body: WatchlistCreateRequest,
    session: Session = Depends(get_db),
) -> WatchlistResponse:
    try:
        row = wl.create_watchlist(
            session,
            name=body.name,
            description=body.description,
            make_default=body.make_default,
        )
        session.commit()
    except wl.WatchlistError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _watchlist_response(session, row)


@router.get("/search", response_model=list[SecuritySearchHitResponse])
def search_securities(
    q: str = Query(min_length=1),
    limit: int = Query(default=20, ge=1, le=50),
    yahoo: bool = Query(default=False),
    session: Session = Depends(get_db),
) -> list[SecuritySearchHitResponse]:
    hits = wl.search_securities_combined(session, q, limit=limit, include_yahoo=yahoo)
    return [
        SecuritySearchHitResponse(
            source=row.source,
            security_id=row.security_id,
            portfolio_name=row.portfolio_name,
            nse_symbol=row.nse_symbol,
            bse_code=row.bse_code,
            isin=row.isin,
            sector=row.sector,
            industry=row.industry,
            yahoo_ticker=row.yahoo_ticker,
        )
        for row in hits
    ]


@router.get("/settings", response_model=WatchlistSettingsResponse)
def watchlist_settings() -> WatchlistSettingsResponse:
    return WatchlistSettingsResponse(
        fundamentals_provider=validated_fundamentals_provider(),
        available_providers=sorted(FUNDAMENTALS_PROVIDERS),
    )


@router.get("/health", response_model=WatchlistsHealthResponse)
def watchlists_health(session: Session = Depends(get_db)) -> WatchlistsHealthResponse:
    report = wh.build_all_watchlists_health(session)
    return WatchlistsHealthResponse(
        fundamentals_provider=report.fundamentals_provider,
        watchlist_count=report.watchlist_count,
        total_members=report.total_members,
        total_unresolved=report.total_unresolved,
        total_stale_resolution=report.total_stale_resolution,
        total_missing_fundamentals=report.total_missing_fundamentals,
        total_stale_fundamentals=report.total_stale_fundamentals,
        total_unacknowledged_alerts=report.total_unacknowledged_alerts,
        any_refresh_locked=report.any_refresh_locked,
        watchlists=[
            WatchlistHealthRowResponse(
                watchlist_id=row.watchlist_id,
                name=row.name,
                member_count=row.member_count,
                resolved_count=row.resolved_count,
                unresolved_count=row.unresolved_count,
                stale_resolution_count=row.stale_resolution_count,
                with_fundamentals_count=row.with_fundamentals_count,
                missing_fundamentals_count=row.missing_fundamentals_count,
                stale_fundamentals_count=row.stale_fundamentals_count,
                unacknowledged_alerts=row.unacknowledged_alerts,
                refresh_locked=row.refresh_locked,
            )
            for row in report.watchlists
        ],
    )


@router.get("/alerts/summary", response_model=AlertSummaryResponse)
def alerts_summary(session: Session = Depends(get_db)) -> AlertSummaryResponse:
    return AlertSummaryResponse(unacknowledged=wa.unacknowledged_count(session))


@router.post("/refresh-all", response_model=SyncWatchlistsResponse)
def refresh_all_watchlists(
    include_fundamentals: bool = Query(default=True),
    session: Session = Depends(get_db),
) -> SyncWatchlistsResponse:
    try:
        result = wr.sync_all_watchlists(
            session,
            include_fundamentals=include_fundamentals,
        )
        session.commit()
    except wl.WatchlistNotFoundError as exc:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except wr.WatchlistRefreshInProgressError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    fundamentals = None
    if result.fundamentals is not None:
        fundamentals = FundamentalsRefreshStatsResponse(
            csv_inserted=result.fundamentals.csv_inserted,
            csv_updated=result.fundamentals.csv_updated,
            csv_skipped=result.fundamentals.csv_skipped,
            csv_invalid=result.fundamentals.csv_invalid,
            snapshots_written=result.fundamentals.snapshots_written,
            identifiers_processed=result.fundamentals.identifiers_processed,
        )
    return SyncWatchlistsResponse(
        watchlists_refreshed=result.watchlists_refreshed,
        fundamentals=fundamentals,
        results=[_refresh_response(row) for row in result.results],
    )


@router.get("/metrics/catalog", response_model=list[MetricDefinitionResponse])
def metric_catalog() -> list[MetricDefinitionResponse]:
    return [
        MetricDefinitionResponse(
            key=metric.key,
            label=metric.label,
            group=metric.group,
            format=metric.format,
            description=metric.description,
        )
        for metric in scr.list_metric_catalog()
    ]


@router.get("/{watchlist_id}/screen")
def watchlist_screen(
    watchlist_id: int,
    columns: str | None = Query(default=None),
    sort: str | None = Query(default=None),
    export: str | None = Query(default=None),
    session: Session = Depends(get_db),
):
    try:
        column_keys = scr.parse_columns(columns)
        rows = scr.build_watchlist_screen(
            session,
            watchlist_id,
            columns=columns,
            sort=sort,
        )
    except wl.WatchlistNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if export == "csv":
        from fastapi.responses import PlainTextResponse

        csv_body = scr.screen_rows_to_csv(rows, column_keys)
        return PlainTextResponse(
            csv_body,
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="watchlist_{watchlist_id}_screen.csv"'
            },
        )

    return WatchlistScreenResponse(
        watchlist_id=watchlist_id,
        columns=list(column_keys),
        sort=sort,
        row_count=len(rows),
        rows=[
            WatchlistScreenRowResponse(
                member_id=row.member_id,
                display_name=row.display_name,
                nse_symbol=row.nse_symbol,
                bse_code=row.bse_code,
                security_id=row.security_id,
                sector=row.sector,
                industry=row.industry,
                resolution_status=row.resolution_status,
                fiscal_year=row.fiscal_year,
                fiscal_quarter=row.fiscal_quarter,
                period_end_date=(
                    row.period_end_date.isoformat() if row.period_end_date else None
                ),
                retrieved_at=row.retrieved_at,
                has_fundamentals=row.has_fundamentals,
                fundamentals_stale=row.fundamentals_stale,
                metrics={
                    key: float(value) if value is not None else None
                    for key, value in row.metrics.items()
                },
            )
            for row in rows
        ],
    )


@router.get("/{watchlist_id}", response_model=WatchlistResponse)
def get_watchlist(
    watchlist_id: int,
    session: Session = Depends(get_db),
) -> WatchlistResponse:
    try:
        row = wl.get_watchlist(session, watchlist_id)
    except wl.WatchlistNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _watchlist_response(session, row)


@router.patch("/{watchlist_id}", response_model=WatchlistResponse)
def update_watchlist(
    watchlist_id: int,
    body: WatchlistUpdateRequest,
    session: Session = Depends(get_db),
) -> WatchlistResponse:
    try:
        row = wl.update_watchlist(
            session,
            watchlist_id,
            name=body.name,
            description=body.description,
            make_default=True if body.make_default else False,
        )
        session.commit()
    except wl.WatchlistNotFoundError as exc:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except wl.WatchlistError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _watchlist_response(session, row)


@router.delete("/{watchlist_id}", status_code=204)
def delete_watchlist(
    watchlist_id: int,
    confirm: bool = Query(default=False),
    session: Session = Depends(get_db),
) -> None:
    try:
        wl.delete_watchlist(session, watchlist_id, confirm=confirm)
        session.commit()
    except wl.WatchlistNotFoundError as exc:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except wl.WatchlistDeleteError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{watchlist_id}/members", response_model=list[WatchlistMemberResponse])
def list_members(
    watchlist_id: int,
    session: Session = Depends(get_db),
) -> list[WatchlistMemberResponse]:
    try:
        rows = wl.list_members(session, watchlist_id)
    except wl.WatchlistNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    status_map = research_status_by_security(
        session, [r.security_id for r in rows if r.security_id]
    )
    return [
        _member_response(row, research_status=_research_status_for_member(row, status_map))
        for row in rows
    ]


@router.post("/{watchlist_id}/members", response_model=WatchlistMemberResponse, status_code=201)
def add_member(
    watchlist_id: int,
    body: WatchlistMemberCreateRequest,
    session: Session = Depends(get_db),
) -> WatchlistMemberResponse:
    try:
        row = wl.add_member(
            session,
            watchlist_id,
            wl.MemberInput(
                portfolio_name=body.portfolio_name,
                security_id=body.security_id,
                nse_symbol=body.nse_symbol,
                bse_code=body.bse_code,
                display_name=body.display_name,
                notes=body.notes,
            ),
        )
        session.flush()
        codes = [row.bse_code] if row.bse_code else []
        if not codes and row.nse_symbol:
            from pms_platform.market_data.bse_scrip_universe import resolve_bse_code

            resolved = resolve_bse_code(
                nse_symbol=row.nse_symbol,
                company_name=row.display_name,
                isin=row.isin,
            )
            if resolved:
                codes = [resolved]
                if not row.bse_code:
                    row.bse_code = resolved
        try:
            wr.enrich_watchlist_for_codes(session, watchlist_id, codes)
        except Exception:
            pass
        session.commit()
        session.refresh(row)
    except wl.WatchlistNotFoundError as exc:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except wl.DuplicateMemberError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except wl.WatchlistError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _member_response(row)


@router.post(
    "/{watchlist_id}/members/bulk",
    response_model=WatchlistBulkMembersResponse,
    status_code=201,
)
def add_members_bulk(
    watchlist_id: int,
    body: WatchlistBulkMembersRequest,
    session: Session = Depends(get_db),
) -> WatchlistBulkMembersResponse:
    names = wl.parse_pasted_names(body.text)
    if not names:
        raise HTTPException(status_code=400, detail="No names to add")
    try:
        result = wl.add_members_by_names(session, watchlist_id, names)
        session.flush()
        try:
            codes = wr._watchlist_bse_codes(session, watchlist_id)
            wr.enrich_watchlist_for_codes(
                session,
                watchlist_id,
                wr.codes_missing_valuation(session, codes),
            )
        except Exception:
            pass
        session.commit()
    except wl.WatchlistNotFoundError as exc:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except wl.WatchlistError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return WatchlistBulkMembersResponse(
        added=result.added, skipped=result.skipped, pending=result.pending
    )


@router.patch(
    "/{watchlist_id}/members/{member_id}",
    response_model=WatchlistMemberResponse,
)
def update_member(
    watchlist_id: int,
    member_id: int,
    body: WatchlistMemberUpdateRequest,
    session: Session = Depends(get_db),
) -> WatchlistMemberResponse:
    try:
        row = wl.update_member_symbols(
            session,
            watchlist_id,
            member_id,
            display_name=body.display_name,
            nse_symbol=body.nse_symbol,
            bse_code=body.bse_code,
            notes=body.notes,
        )
        session.flush()
        if row.bse_code:
            try:
                wr.enrich_watchlist_for_codes(session, watchlist_id, [row.bse_code])
            except Exception:
                pass
        session.commit()
    except wl.WatchlistNotFoundError as exc:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except wl.WatchlistMemberNotFoundError as exc:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except wl.WatchlistError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _member_response(row)


@router.post(
    "/{watchlist_id}/members/{member_id}/resolve",
    response_model=WatchlistMemberResponse,
)
def resolve_member(
    watchlist_id: int,
    member_id: int,
    session: Session = Depends(get_db),
) -> WatchlistMemberResponse:
    try:
        row = wl.resolve_watchlist_member(session, watchlist_id, member_id)
        session.flush()
        if row.bse_code:
            try:
                wr.enrich_watchlist_for_codes(session, watchlist_id, [row.bse_code])
            except Exception:
                pass
        session.commit()
    except wl.WatchlistNotFoundError as exc:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except wl.WatchlistMemberNotFoundError as exc:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _member_response(row)


@router.post("/{watchlist_id}/resolve", response_model=ResolveWatchlistResponse)
def resolve_watchlist(
    watchlist_id: int,
    session: Session = Depends(get_db),
) -> ResolveWatchlistResponse:
    try:
        stats = wl.resolve_stale_members(session, watchlist_id)
        session.flush()
        try:
            codes = wr._watchlist_bse_codes(session, watchlist_id)
            wr.enrich_watchlist_for_codes(
                session,
                watchlist_id,
                wr.codes_missing_valuation(session, codes),
            )
        except Exception:
            pass
        session.commit()
    except wl.WatchlistNotFoundError as exc:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ResolveWatchlistResponse(**stats)


@router.get("/{watchlist_id}/health", response_model=WatchlistHealthRowResponse)
def watchlist_health(
    watchlist_id: int,
    session: Session = Depends(get_db),
) -> WatchlistHealthRowResponse:
    try:
        row = wh.build_watchlist_health(session, watchlist_id)
    except wl.WatchlistNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return WatchlistHealthRowResponse(
        watchlist_id=row.watchlist_id,
        name=row.name,
        member_count=row.member_count,
        resolved_count=row.resolved_count,
        unresolved_count=row.unresolved_count,
        stale_resolution_count=row.stale_resolution_count,
        with_fundamentals_count=row.with_fundamentals_count,
        missing_fundamentals_count=row.missing_fundamentals_count,
        stale_fundamentals_count=row.stale_fundamentals_count,
        unacknowledged_alerts=row.unacknowledged_alerts,
        refresh_locked=row.refresh_locked,
    )


@router.get("/{watchlist_id}/export")
def export_watchlist(
    watchlist_id: int,
    export_format: str = Query(default="json", alias="format", pattern="^(json|csv)$"),
    session: Session = Depends(get_db),
):
    from fastapi.responses import PlainTextResponse

    try:
        if export_format == "csv":
            body = wi.export_watchlist_csv(session, watchlist_id)
            return PlainTextResponse(
                body,
                media_type="text/csv",
                headers={
                    "Content-Disposition": f'attachment; filename="watchlist_{watchlist_id}.csv"'
                },
            )
        body = wi.export_watchlist_json_text(session, watchlist_id)
        return PlainTextResponse(
            body,
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="watchlist_{watchlist_id}.json"'
            },
        )
    except wl.WatchlistNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/import", response_model=WatchlistImportResponse, status_code=201)
def import_watchlist(
    body: WatchlistImportRequest,
    session: Session = Depends(get_db),
) -> WatchlistImportResponse:
    try:
        result = wi.import_watchlist_json(
            session,
            body.payload,
            watchlist_id=body.watchlist_id,
            create_name=body.create_name,
        )
        session.commit()
    except wl.WatchlistError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except wl.WatchlistNotFoundError as exc:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return WatchlistImportResponse(
        watchlist_id=result.watchlist_id,
        watchlist_name=result.watchlist_name,
        members_added=result.members_added,
        members_skipped=result.members_skipped,
    )


@router.post("/{watchlist_id}/refresh", response_model=WatchlistRefreshResponse)
def refresh_watchlist(
    watchlist_id: int,
    include_fundamentals: bool = Query(default=True),
    session: Session = Depends(get_db),
) -> WatchlistRefreshResponse:
    try:
        result = wr.refresh_watchlist(
            session,
            watchlist_id,
            include_fundamentals=include_fundamentals,
        )
        session.commit()
    except wl.WatchlistNotFoundError as exc:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except wr.WatchlistRefreshInProgressError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _refresh_response(result)


@router.get("/{watchlist_id}/alerts", response_model=list[WatchlistAlertResponse])
def list_watchlist_alerts(
    watchlist_id: int,
    unacknowledged_only: bool = Query(default=False),
    refresh: bool = Query(default=False),
    session: Session = Depends(get_db),
) -> list[WatchlistAlertResponse]:
    try:
        if refresh:
            wa.poll_watchlist_alerts(session, watchlist_id)
            session.commit()
        rows = wa.list_alerts(session, watchlist_id, unacknowledged_only=unacknowledged_only)
    except wl.WatchlistNotFoundError as exc:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [_alert_response(row) for row in rows]


@router.post("/{watchlist_id}/alerts/poll", response_model=AlertPollResponse)
def poll_watchlist_alerts(
    watchlist_id: int,
    session: Session = Depends(get_db),
) -> AlertPollResponse:
    try:
        result = wa.poll_watchlist_alerts(session, watchlist_id)
        session.commit()
    except wl.WatchlistNotFoundError as exc:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return AlertPollResponse(
        inserted=result.inserted,
        skipped=result.skipped,
        matched=result.matched,
    )


@router.post(
    "/{watchlist_id}/alerts/{alert_id}/acknowledge",
    response_model=WatchlistAlertResponse,
)
def acknowledge_watchlist_alert(
    watchlist_id: int,
    alert_id: int,
    session: Session = Depends(get_db),
) -> WatchlistAlertResponse:
    try:
        row = wa.acknowledge_alert(session, watchlist_id, alert_id)
        session.commit()
    except wl.WatchlistAlertNotFoundError as exc:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _alert_response(row)


@router.delete("/{watchlist_id}/members/{member_id}", status_code=204)
def remove_member(
    watchlist_id: int,
    member_id: int,
    session: Session = Depends(get_db),
) -> None:
    try:
        wl.remove_member(session, watchlist_id, member_id)
        session.commit()
    except wl.WatchlistNotFoundError as exc:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except wl.WatchlistMemberNotFoundError as exc:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
