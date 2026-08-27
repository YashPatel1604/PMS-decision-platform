"""Pivot firm selection store and working-view overlays."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from pms_platform.market_data.pivot_dashboard import HIDDEN_PIVOT_SYMBOLS
from pms_platform.models.change_request import ChangeOperation, ChangeRequest
from pms_platform.models.pivot_selection import PivotFirmSelection
from pms_platform.read_context import ReadContext, ReadMode


def official_selection(session: Session) -> list[str]:
    rows = session.scalars(
        select(PivotFirmSelection).order_by(
            PivotFirmSelection.sort_order, PivotFirmSelection.symbol
        )
    ).all()
    return [r.symbol for r in rows if r.symbol not in HIDDEN_PIVOT_SYMBOLS]


def selection_row_version(session: Session) -> int:
    rows = session.scalars(select(PivotFirmSelection)).all()
    if not rows:
        return 1
    return max(r.row_version for r in rows)


def replace_official_selection(
    session: Session,
    symbols: list[str],
    *,
    base_row_version: int,
    updated_by: int,
) -> None:
    clean = []
    seen: set[str] = set()
    for sym in symbols:
        key = sym.strip().upper()
        if not key or key in HIDDEN_PIVOT_SYMBOLS or key in seen:
            continue
        seen.add(key)
        clean.append(key)
    current_v = selection_row_version(session)
    existing = session.scalars(select(PivotFirmSelection)).all()
    if existing and current_v != base_row_version:
        raise ValueError("row_version conflict")
    session.execute(delete(PivotFirmSelection))
    for idx, symbol in enumerate(clean):
        session.add(
            PivotFirmSelection(
                symbol=symbol,
                sort_order=idx,
                row_version=current_v + 1 if existing else 1,
            )
        )
    session.flush()


def _overlay_ops(session: Session, ctx: ReadContext) -> list[ChangeOperation]:
    if ctx.mode == ReadMode.OFFICIAL:
        return []
    q = (
        select(ChangeOperation)
        .join(ChangeRequest, ChangeOperation.change_request_id == ChangeRequest.change_request_id)
        .where(
            ChangeRequest.domain == "pivot",
            ChangeOperation.entity_kind == "pivot_firm_selection",
        )
    )
    if ctx.mode == ReadMode.MINE:
        q = q.where(
            ChangeRequest.proposer_user_id == ctx.viewer_user_id,
            ChangeRequest.status.in_(("draft", "submitted")),
        )
    elif ctx.mode == ReadMode.PROPOSAL:
        q = q.where(ChangeRequest.change_request_id == ctx.change_request_id)
    else:
        return []
    return list(session.scalars(q.order_by(ChangeOperation.operation_order.desc())).all())


def resolve_selection(
    session: Session,
    ctx: ReadContext | None,
    *,
    fallback_portfolio_symbols: list[str],
) -> dict[str, Any]:
    """Official list plus optional working overlay from active change request."""
    official = official_selection(session)
    if not official and fallback_portfolio_symbols:
        official = [
            s for s in fallback_portfolio_symbols if s.upper() not in HIDDEN_PIVOT_SYMBOLS
        ]
    out: dict[str, Any] = {
        "symbols": official,
        "row_version": selection_row_version(session),
        "change_status": None,
        "proposed_symbols": None,
        "change_request_id": None,
    }
    if ctx is None or ctx.mode == ReadMode.OFFICIAL:
        return out

    for op in _overlay_ops(session, ctx):
        req = session.get(ChangeRequest, op.change_request_id)
        if req is None:
            continue
        proposed = (op.after_state or {}).get("symbols")
        if isinstance(proposed, list):
            out["symbols"] = [str(s).upper() for s in proposed if str(s).strip()]
            out["proposed_symbols"] = out["symbols"]
            out["approved_symbols"] = official
        out["change_status"] = req.status
        out["change_request_id"] = str(req.change_request_id)
        break
    return out
