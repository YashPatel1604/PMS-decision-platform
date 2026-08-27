"""Apply approved client position quantity changes."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from pms_platform.approval.handlers.registry import register_handler
from pms_platform.domain.client_positions import apply_approved_qty_change


class ClientPositionHandler:
    entity_kind = "client_position"

    def validate_operation(self, operation: dict[str, Any]) -> dict[str, Any]:
        after = operation.get("after_state") or {}
        qty = after.get("qty")
        if qty is None:
            raise ValueError("qty required")
        Decimal(str(qty))
        return {"ok": True}

    def apply_operation(self, session: Session, operation: dict[str, Any]) -> None:
        symbol = operation.get("entity_id")
        after = operation.get("after_state") or {}
        if not symbol:
            raise ValueError("entity_id required")
        base_v = operation.get("base_row_version") or 1
        book = (after.get("book") or "client").strip().lower()
        apply_approved_qty_change(
            session,
            symbol=str(symbol),
            qty=Decimal(str(after["qty"])),
            base_row_version=int(base_v),
            updated_by=int(operation.get("updated_by") or 0),
            book=book,
        )


_handler = ClientPositionHandler()
register_handler(_handler)
