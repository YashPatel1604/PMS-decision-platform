"""Client position canonical store and working-view overlays."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.market_data.client_portfolio_parse import mcap_and_firm_at_price
from pms_platform.models.change_request import ChangeOperation, ChangeRequest
from pms_platform.models.client_book_settings import ClientBookSettings
from pms_platform.models.client_position import ClientPosition
from pms_platform.read_context import ReadContext, ReadMode


def holdings_domain(book: str) -> str:
    return "sca_portfolio" if (book or "").strip().lower() == "sca" else "client_portfolio"


def official_positions(session: Session, *, book: str = "client") -> dict[str, ClientPosition]:
    return {
        row.symbol: row
        for row in session.scalars(select(ClientPosition).where(ClientPosition.book == book)).all()
    }


def official_qty_map(session: Session, *, book: str = "client") -> dict[str, ClientPosition]:
    return official_positions(session, book=book)


def sync_positions_from_holdings(
    session: Session,
    holdings: list[dict[str, Any]],
    *,
    book: str = "client",
) -> None:
    """Seed missing approved rows from Excel-derived holdings (idempotent)."""
    existing = official_positions(session, book=book)
    for row in holdings:
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        qty = row.get("qty")
        if qty is None:
            continue
        mcap_factor = row.get("mcap_factor")
        index_label = row.get("index_label")
        if symbol in existing:
            pos = existing[symbol]
            if pos.mcap_factor is None and mcap_factor is not None:
                pos.mcap_factor = Decimal(str(mcap_factor))
            if pos.index_label is None and index_label:
                pos.index_label = str(index_label).strip() or None
            continue
        session.add(
            ClientPosition(
                book=book,
                symbol=symbol,
                qty=Decimal(str(qty)),
                mcap_factor=Decimal(str(mcap_factor)) if mcap_factor is not None else None,
                index_label=str(index_label).strip() if index_label else None,
                row_version=1,
            )
        )


def apply_canonical_field_overlay(
    session: Session,
    holdings: list[dict[str, Any]],
    *,
    book: str = "client",
) -> None:
    """Apply stored mcap_factor / index_label and recompute derived mcap / %Firm."""
    sync_positions_from_holdings(session, holdings, book=book)
    official = official_positions(session, book=book)
    for row in holdings:
        symbol = str(row["symbol"]).upper()
        pos = official.get(symbol)
        if pos is None:
            continue
        if pos.index_label is not None:
            row["index_label"] = pos.index_label
        if pos.mcap_factor is not None:
            row["mcap_factor"] = float(pos.mcap_factor)
            price = row.get("close") or row.get("price")
            if price is not None:
                stocks_qty = row.get("stocks_qty")
                qty = row.get("qty")
                sq = stocks_qty if stocks_qty is not None else qty
                live_mcap, live_firm = mcap_and_firm_at_price(
                    mcap_factor=pos.mcap_factor,
                    price=Decimal(str(price)),
                    stocks_qty=Decimal(str(sq)) if sq is not None else None,
                )
                if live_mcap is not None:
                    row["mcap"] = float(live_mcap)
                if live_firm is not None:
                    row["firm_pct"] = float(live_firm)


def update_position_fields(
    session: Session,
    *,
    symbol: str,
    book: str,
    updated_by: int,
    index_label: str | None = None,
    mcap_factor: Decimal | None = None,
    touch_index: bool = False,
    touch_mcap_factor: bool = False,
) -> ClientPosition:
    sym = symbol.strip().upper()
    book_key = (book or "client").strip().lower()
    pos = session.scalar(
        select(ClientPosition).where(ClientPosition.book == book_key, ClientPosition.symbol == sym)
    )
    if pos is None:
        pos = ClientPosition(book=book_key, symbol=sym, qty=Decimal(0), row_version=1)
        session.add(pos)
        session.flush()
    if touch_index:
        pos.index_label = index_label.strip() if index_label else None
    if touch_mcap_factor:
        pos.mcap_factor = mcap_factor
    pos.row_version = pos.row_version + 1
    pos.updated_by = updated_by
    session.flush()
    return pos


def bank_balance_for_book(
    session: Session,
    book: str,
    *,
    excel_bank: Decimal | None = None,
) -> Decimal | None:
    """Return canonical bank balance, seeding from Excel once when missing."""
    book_key = (book or "client").strip().lower()
    settings = session.get(ClientBookSettings, book_key)
    if settings is None:
        if excel_bank is None:
            return None
        settings = ClientBookSettings(book=book_key, bank_balance=excel_bank)
        session.add(settings)
        session.flush()
        return excel_bank
    if settings.bank_balance is not None:
        return settings.bank_balance
    if excel_bank is not None:
        settings.bank_balance = excel_bank
        session.flush()
        return excel_bank
    return None


def set_bank_balance(
    session: Session,
    *,
    book: str,
    amount: Decimal,
    updated_by: int,
) -> Decimal:
    book_key = (book or "client").strip().lower()
    settings = session.get(ClientBookSettings, book_key)
    if settings is None:
        settings = ClientBookSettings(book=book_key, bank_balance=amount)
        session.add(settings)
    else:
        settings.bank_balance = amount
        settings.row_version = settings.row_version + 1
    settings.updated_by = updated_by
    session.flush()
    return settings.bank_balance


def _active_overlay_ops(
    session: Session,
    ctx: ReadContext,
    *,
    domain: str,
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
    official = official_positions(session, book=book)
    overlays = _active_overlay_ops(session, ctx, domain=holdings_domain(book))
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


def book_from_official_positions(session: Session, *, book: str = "client"):
    """Build a ClientPortfolioBook from approved DB rows (cloud when Excel is absent)."""
    from pms_platform.market_data.client_portfolio_parse import (
        ClientPortfolioBook,
        ClientPortfolioPosition,
    )

    positions = official_positions(session, book=book)
    if not positions:
        return None
    model = [
        ClientPortfolioPosition(
            symbol=sym,
            qty=pos.qty,
            excel_price=None,
            excel_value=None,
            excel_percent=None,
            index_label=pos.index_label,
            mcap_factor=pos.mcap_factor,
        )
        for sym, pos in sorted(positions.items())
    ]
    bank_balance = None
    if book == "sca":
        bank_balance = bank_balance_for_book(session, book, excel_bank=None)
    return ClientPortfolioBook(
        path=Path("db://client_positions"),
        mtime=0.0,
        model=model,
        stocks_qty={sym: pos.qty for sym, pos in positions.items()},
        excel_total_value=None,
        yearly=(),
        bank_balance=bank_balance,
    )


def resolve_client_portfolio_book(
    session: Session,
    *,
    path: Path | None = None,
    book: str = "client",
):
    """Excel workbook when present; else approved DB positions when workflow is on."""
    from pms_platform.feature_flags import approval_workflow_enabled
    from pms_platform.market_data.client_portfolio_parse import load_client_portfolio_book

    loaded = load_client_portfolio_book(path)
    if loaded is not None:
        return loaded
    if approval_workflow_enabled():
        return book_from_official_positions(session, book=book)
    return None


def reimport_client_positions(
    session: Session,
    holdings: list[dict[str, Any]],
    *,
    book: str = "client",
    update_qty: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Sync symbol add/remove and metadata from Excel; qty only when update_qty."""
    book_key = (book or "client").strip().lower()
    excel_symbols: dict[str, dict[str, Any]] = {}
    for row in holdings:
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        excel_symbols[symbol] = row

    official = official_positions(session, book=book_key)
    added = sorted(set(excel_symbols) - set(official))
    removed = sorted(set(official) - set(excel_symbols))
    metadata_updated: list[str] = []
    qty_updated: list[str] = []

    for symbol, row in excel_symbols.items():
        pos = official.get(symbol)
        mcap_factor = row.get("mcap_factor")
        index_label = row.get("index_label")
        qty = row.get("qty")
        if pos is None:
            continue
        if mcap_factor is not None and (
            pos.mcap_factor is None or pos.mcap_factor != Decimal(str(mcap_factor))
        ):
            metadata_updated.append(symbol)
        elif index_label and (pos.index_label or "") != str(index_label).strip():
            metadata_updated.append(symbol)
        if update_qty and qty is not None and pos.qty != Decimal(str(qty)):
            qty_updated.append(symbol)

    if dry_run:
        return {
            "added": added,
            "removed": removed,
            "metadata_updated": sorted(set(metadata_updated)),
            "qty_updated": qty_updated,
        }

    for symbol in removed:
        session.delete(official[symbol])
    for symbol in added:
        row = excel_symbols[symbol]
        qty = row.get("qty")
        session.add(
            ClientPosition(
                book=book_key,
                symbol=symbol,
                qty=Decimal(str(qty)) if qty is not None else Decimal(0),
                mcap_factor=Decimal(str(row["mcap_factor"]))
                if row.get("mcap_factor") is not None
                else None,
                index_label=str(row["index_label"]).strip() if row.get("index_label") else None,
                row_version=1,
            )
        )
    session.flush()
    official = official_positions(session, book=book_key)
    for symbol, row in excel_symbols.items():
        pos = official.get(symbol)
        if pos is None:
            continue
        if row.get("mcap_factor") is not None:
            pos.mcap_factor = Decimal(str(row["mcap_factor"]))
        if row.get("index_label"):
            pos.index_label = str(row["index_label"]).strip() or None
        if update_qty and row.get("qty") is not None:
            pos.qty = Decimal(str(row["qty"]))
        pos.row_version = pos.row_version + 1
    session.flush()
    return {
        "added": added,
        "removed": removed,
        "metadata_updated": sorted(set(metadata_updated)),
        "qty_updated": qty_updated,
    }
