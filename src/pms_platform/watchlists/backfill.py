"""Resumable watchlist data backfill orchestrator."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from pms_platform.config import settings
from pms_platform.fundamentals.service import recompute_snapshots_for_identifiers, sync_fundamentals
from pms_platform.fundamentals.valuation_derived import enrich_derived_valuations
from pms_platform.market_data.price_returns import refresh_price_returns
from pms_platform.market_data.repair_prices import repair_security_prices_from_yahoo
from pms_platform.models.daily_price import DailyPrice
from pms_platform.models.watchlist import WatchlistMember
from pms_platform.watchlists import service as wl
from pms_platform.watchlists.member_context import count_prices
from pms_platform.watchlists.metric_diagnostics import bse_code
from pms_platform.watchlists.metrics_cache import rebuild_all_watchlist_metrics, rebuild_watchlist_metrics
from pms_platform.watchlists.refresh import (
    _all_watchlist_bse_codes,
    _all_watchlist_nse_targets,
    _watchlist_bse_codes,
    _watchlist_nse_targets,
)

PASSES = (
    "identity",
    "prices",
    "financials",
    "valuation",
    "metrics",
)


@dataclass
class BackfillOptions:
    watchlist_id: int | None = None
    security_id: str | None = None
    nse_symbol: str | None = None
    missing_only: bool = True
    financial_history: bool = False
    missing_history_only: bool = True
    annual_history: bool = False
    alias_history: bool = False
    financials: bool = True
    prices: bool = True
    valuation: bool = True
    rebuild_metrics: bool = True
    force: bool = False
    max_concurrency: int = 1  # ponytail: sequential remote calls; raise when stable


@dataclass
class BackfillResult:
    members_total: int
    passes_run: list[str]
    resolution_resolved: int = 0
    prices_repaired: int = 0
    prices_skipped: int = 0
    financials_codes: int = 0
    valuation_updated: int = 0
    metrics_rows: int = 0
    errors: list[str] = field(default_factory=list)


def _state_path() -> Path:
    path = settings.external_data_dir / "watchlist_backfill_state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_state() -> dict[str, Any]:
    path = _state_path()
    if not path.exists():
        return {"completed_passes": [], "members_done": {}, "financials_done": []}
    state = json.loads(path.read_text(encoding="utf-8"))
    state.setdefault("members_done", {})
    state.setdefault("financials_done", [])
    return state


def _save_state(state: dict[str, Any]) -> None:
    _state_path().write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


def _select_members(session: Session, opts: BackfillOptions) -> list[WatchlistMember]:
    q = select(WatchlistMember).options(joinedload(WatchlistMember.security))
    if opts.watchlist_id is not None:
        q = q.where(WatchlistMember.watchlist_id == opts.watchlist_id)
    if opts.security_id:
        q = q.where(WatchlistMember.security_id == opts.security_id)
    if opts.nse_symbol:
        q = q.where(WatchlistMember.nse_symbol == opts.nse_symbol.strip().upper())
    return list(session.scalars(q).all())


def _pass_identity(session: Session, members: list[WatchlistMember], opts: BackfillOptions) -> int:
    from pms_platform.watchlists import identity_link as il

    resolved = 0
    if opts.watchlist_id is not None:
        watchlist_ids = {opts.watchlist_id}
    else:
        watchlist_ids = {w.watchlist_id for w in wl.list_watchlists(session)}
    for wid in watchlist_ids:
        raw = wl.resolve_stale_members(session, wid)
        resolved += int(raw.get("resolved", 0))
    session.flush()
    link_stats = il.link_watchlist_members(session, watchlist_id=opts.watchlist_id)
    resolved += link_stats.linked
    session.flush()
    if opts.security_id or opts.nse_symbol:
        for member in members:
            if not member.security_id:
                il.link_watchlist_member(session, member)
                session.refresh(member)
                if member.security_id:
                    resolved += 1
        session.flush()
    return resolved


def _members_needing_prices(session: Session, members: list[WatchlistMember]) -> list[WatchlistMember]:
    out: list[WatchlistMember] = []
    for member in members:
        if not member.security_id:
            continue
        bse = bse_code(member)
        if count_prices(session, member, bse) == 0:
            out.append(member)
    return out


def _pass_prices(session: Session, members: list[WatchlistMember], opts: BackfillOptions) -> tuple[int, int]:
    targets = _members_needing_prices(session, members)
    if opts.missing_only is False:
        targets = [m for m in members if m.security_id]

    from pms_platform.models import Security

    repaired = skipped = 0
    for member in targets:
        sec_id = member.security_id
        if not sec_id:
            skipped += 1
            continue
        try:
            repair_security_prices_from_yahoo(session, security_id=sec_id)
            repaired += 1
        except Exception:
            skipped += 1
        time.sleep(0.25)
    session.flush()
    return repaired, skipped


def _nse_target_for_member(session: Session, member: WatchlistMember):
    from pms_platform.fundamentals.providers.nse import NseTarget
    from pms_platform.watchlists.financial_discovery import build_financial_discovery_identities

    bse = bse_code(member)
    nse = str(member.nse_symbol or "").strip().upper()
    if member.security_id:
        ids = build_financial_discovery_identities(session, member.security_id)
        if ids and ids.current_nse_symbol:
            nse = ids.current_nse_symbol
        if ids and ids.current_bse_code:
            bse = ids.current_bse_code
    if not nse or not bse:
        return None
    return NseTarget(nse_symbol=nse, bse_code=bse, security_id=member.security_id)


def _member_needs_financial_history(session: Session, member: WatchlistMember) -> bool:
    from pms_platform.watchlists.history_audit import classify_member_history

    if not member.security_id or not bse_code(member):
        return False
    gap = classify_member_history(session, member)
    return bool(gap.cagr_5y_classification or gap.annual_quality_classification)


def _pass_financials_targeted(
    session: Session,
    members: list[WatchlistMember],
    opts: BackfillOptions,
    state: dict[str, Any],
    errors: list[str],
) -> int:
    """Per-security financial discovery with isolated failures and checkpoint."""
    from pms_platform.fundamentals.providers.annual_xbrl import refresh_annual_fundamentals
    from pms_platform.fundamentals.service import recompute_snapshots_for_identifiers, sync_fundamentals

    done: set[str] = set(state.get("financials_done") or [])
    if opts.force:
        done = set()

    targets = [m for m in members if m.security_id and bse_code(m)]
    if opts.missing_history_only:
        targets = [m for m in targets if _member_needs_financial_history(session, m)]

    processed = 0
    for member in targets:
        sec_id = member.security_id
        if not sec_id or sec_id in done:
            continue
        bse = bse_code(member)
        if not bse:
            continue
        nse_target = _nse_target_for_member(session, member)
        try:
            sync_fundamentals(
                session,
                bse_codes=[bse],
                nse_targets=[nse_target] if nse_target else None,
                include_valuation=False,
                include_annual=False,
                include_price_returns=False,
            )
            refresh_annual_fundamentals(
                session,
                [bse],
                years_back=8 if opts.financial_history else 1,
                request_delay_sec=0.15,
            )
            recompute_snapshots_for_identifiers(session, [("BSE_CODE", bse)])
            session.commit()
            done.add(sec_id)
            state["financials_done"] = sorted(done)
            _save_state(state)
            processed += 1
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            errors.append(
                f"financials {member.display_name} ({sec_id}/{bse}): {exc}"
            )
        time.sleep(0.25)
    return processed


def _pass_financials(
    session: Session,
    members: list[WatchlistMember],
    opts: BackfillOptions,
    errors: list[str] | None = None,
) -> int:
    if not opts.financials:
        return 0
    if opts.financial_history:
        state = _load_state()
        fin_errors: list[str] = errors if errors is not None else []
        count = _pass_financials_targeted(session, members, opts, state, fin_errors)
        if errors is None and fin_errors:
            raise RuntimeError("; ".join(fin_errors[:3]))
        return count
    if opts.watchlist_id is not None:
        codes = _watchlist_bse_codes(session, opts.watchlist_id)
        nse_targets = _watchlist_nse_targets(session, opts.watchlist_id)
    else:
        codes = _all_watchlist_bse_codes(session)
        nse_targets = _all_watchlist_nse_targets(session)
    if opts.missing_only:
        from pms_platform.watchlists.refresh import codes_missing_valuation

        missing_val = set(codes_missing_valuation(session, codes))
        codes = [c for c in codes if c in missing_val] or codes
    sync_fundamentals(
        session,
        bse_codes=codes or None,
        nse_targets=nse_targets or None,
    )
    touched = [("BSE_CODE", c) for c in codes]
    if touched:
        recompute_snapshots_for_identifiers(session, touched)
    return len(codes)


def _pass_valuation(session: Session, members: list[WatchlistMember], opts: BackfillOptions) -> int:
    if not opts.valuation:
        return 0
    codes: list[str] = []
    for member in members:
        bse = bse_code(member)
        if bse and bse not in codes:
            codes.append(bse)
    if not codes:
        return 0
    from pms_platform.fundamentals.providers.valuation import refresh_valuation_snapshots
    from pms_platform.fundamentals.service import _valuation_enrichment

    trailing_sales, pat_cagr = _valuation_enrichment(session, codes)
    refresh_valuation_snapshots(
        session,
        codes,
        force=opts.force,
        trailing_sales_by_code=trailing_sales,
        pat_3y_cagr_by_code=pat_cagr,
    )
    result = enrich_derived_valuations(session, codes, force=opts.force)
    refresh_price_returns(session, [("BSE_CODE", c) for c in codes])
    return result.updated


def _pass_metrics(session: Session, opts: BackfillOptions) -> int:
    if not opts.rebuild_metrics:
        return 0
    if opts.watchlist_id is not None:
        return rebuild_watchlist_metrics(session, opts.watchlist_id)
    return rebuild_all_watchlist_metrics(session)


def _pass_annual_history(session: Session, members: list[WatchlistMember], opts: BackfillOptions) -> int:
    from pms_platform.fundamentals.annual_history import (
        refresh_alias_financial_history,
        refresh_watchlist_annual_history,
    )

    if opts.alias_history:
        refresh_alias_financial_history(session)
    result = refresh_watchlist_annual_history(
        session,
        watchlist_id=opts.watchlist_id,
        security_id=opts.security_id,
        years_back=8,
    )
    return result.securities_processed


def backfill_watchlist_data(session: Session, opts: BackfillOptions) -> BackfillResult:
    """Run ordered backfill passes; checkpoint after each pass."""
    members = _select_members(session, opts)
    state = _load_state()
    completed = set(state.get("completed_passes") or [])
    if opts.force:
        completed = set()
        state["completed_passes"] = []

    result = BackfillResult(members_total=len(members), passes_run=[])

    if "identity" not in completed:
        result.resolution_resolved = _pass_identity(session, members, opts)
        completed.add("identity")
        state["completed_passes"] = sorted(completed)
        _save_state(state)
        session.commit()
        result.passes_run.append("identity")

    if opts.prices and "prices" not in completed:
        rep, skip = _pass_prices(session, members, opts)
        result.prices_repaired = rep
        result.prices_skipped = skip
        completed.add("prices")
        state["completed_passes"] = sorted(completed)
        _save_state(state)
        session.commit()
        result.passes_run.append("prices")

    if opts.annual_history and "annual_history" not in completed:
        try:
            result.financials_codes = _pass_annual_history(session, members, opts)
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"annual_history: {exc}")
            session.rollback()
        else:
            completed.add("annual_history")
            state["completed_passes"] = sorted(completed)
            _save_state(state)
            session.commit()
            result.passes_run.append("annual_history")

    if opts.financials and (opts.financial_history or "financials" not in completed):
        fin_errors: list[str] = []
        try:
            result.financials_codes = _pass_financials(session, members, opts, fin_errors)
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"financials: {exc}")
            session.rollback()
        else:
            result.errors.extend(fin_errors)
            if not fin_errors:
                completed.add("financials")
                state["completed_passes"] = sorted(completed)
                _save_state(state)
            if opts.financial_history or not fin_errors:
                session.commit()
            result.passes_run.append("financials")

    if opts.valuation and "valuation" not in completed:
        result.valuation_updated = _pass_valuation(session, members, opts)
        completed.add("valuation")
        state["completed_passes"] = sorted(completed)
        _save_state(state)
        session.commit()
        result.passes_run.append("valuation")

    if opts.rebuild_metrics and "metrics" not in completed:
        result.metrics_rows = _pass_metrics(session, opts)
        completed.add("metrics")
        state["completed_passes"] = sorted(completed)
        _save_state(state)
        session.commit()
        result.passes_run.append("metrics")

    return result
