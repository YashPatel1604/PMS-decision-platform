"""Client position canonical store and working-view overlays."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.models.change_request import ChangeOperation, ChangeRequest
from pms_platform.models.client_position import ClientPosition
from pms_platform.read_context import ReadContext, ReadMode


def sync_positions_from_holdings(
    session: Session,
    holdings: list[dict[str, Any]],
    *,
    book: str = "client",
) -> None:
    """Seed missing approved rows from Excel-derived holdings (idempotent)."""
    existing = {
        row.symbol: row
        for row in session.scalars(
            select(ClientPosition).where(ClientPosition.book == book)
        ).all()
    }
    for row in holdings:
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        qty = row.get("qty")
        if qty is None:
            continue
        if symbol in existing:
            continue
        session.add(
            ClientPosition(
                book=book,
                symbol=symbol,
                qty=Decimal(str(qty)),
                row_version=1,
            )
        )


def official_qty_map(session: Session, *, book: str = "client") -> dict[str, ClientPosition]:
    return {
        row.symbol: row
        for row in session.scalars(select(ClientPosition).where(ClientPosition.book == book)).all()
    }


def _active_overlay_ops(
    session: Session,
    ctx: ReadContext,
    *,
    domain: str = "client_portfolio",
) -> list[ChangeOperation]:
    if ctx.mode == ReadMode.OFFICIAL:
        return []
    q = (
        select(ChangeOperation)
        .join(ChangeRequest, ChangeOperation.change_request_id == ChangeRequest.change_request_id)
        .where(
            ChangeRequest.domain == domain,
            ChangeOperation.entity_kind == "client_position",
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
    return list(session.scalars(q.order_by(ChangeOperation.operation_order)).all())


def apply_qty_overlay(
    session: Session,
    holdings: list[dict[str, Any]],
    ctx: ReadContext,
    *,
    book: str = "client",
) -> list[dict[str, Any]]:
    """Return holdings with qty overlay + change metadata for UI."""
    sync_positions_from_holdings(session, holdings, book=book)
    official = official_qty_map(session, book=book)
    overlays = _active_overlay_ops(session, ctx)
    overlay_by_symbol: dict[str, tuple[ChangeOperation, ChangeRequest]] = {}
    for op in overlays:
        req = session.get(ChangeRequest, op.change_request_id)
        if req is None or not op.entity_id:
            continue
        overlay_by_symbol[op.entity_id.upper()] = (op, req)

    out: list[dict[str, Any]] = []
    for row in holdings:
        symbol = str(row["symbol"]).upper()
        copy = dict(row)
        pos = official.get(symbol)
        official_qty = float(pos.qty) if pos is not None else copy.get("qty")
        copy["qty"] = official_qty
        copy["row_version"] = pos.row_version if pos is not None else None
        copy["change_status"] = None
        copy["proposed_qty"] = None
        copy["change_request_id"] = None
        if symbol in overlay_by_symbol:
            op, req = overlay_by_symbol[symbol]
            proposed = op.after_state.get("qty") if op.after_state else None
            if proposed is not None:
                copy["proposed_qty"] = float(proposed)
                copy["qty"] = float(proposed)
            copy["change_status"] = req.status
            copy["change_request_id"] = str(req.change_request_id)
            copy["approved_qty"] = official_qty
        out.append(copy)
    return out


def apply_approved_qty_change(
    session: Session,
    *,
    symbol: str,
    qty: Decimal,
    base_row_version: int,
    updated_by: int,
    book: str = "client",
) -> ClientPosition:
    pos = session.scalar(
        select(ClientPosition).where(
            ClientPosition.book == book, ClientPosition.symbol == symbol.upper()
        )
    )
    if pos is None:
        pos = ClientPosition(book=book, symbol=symbol.upper(), qty=qty, row_version=1, updated_by=updated_by)
        session.add(pos)
        session.flush()
        return pos
    if pos.row_version != base_row_version:
        raise ValueError("row_version conflict")
    pos.qty = qty
    pos.row_version = pos.row_version + 1
    pos.updated_by = updated_by
    session.flush()
    return pos
