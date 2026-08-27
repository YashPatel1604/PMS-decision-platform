"""Apply approved pivot firm selection changes."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from pms_platform.approval.handlers.registry import register_handler
from pms_platform.domain.pivot_selection import replace_official_selection


class PivotFirmSelectionHandler:
    entity_kind = "pivot_firm_selection"

    def validate_operation(self, operation: dict[str, Any]) -> dict[str, Any]:
        after = operation.get("after_state") or {}
        symbols = after.get("symbols")
        if not isinstance(symbols, list):
            raise ValueError("symbols list required")
        return {"ok": True, "count": len(symbols)}

    def apply_operation(self, session: Session, operation: dict[str, Any]) -> None:
        after = operation.get("after_state") or {}
        symbols = after.get("symbols") or []
        base_v = int(operation.get("base_row_version") or 1)
        replace_official_selection(
            session,
            [str(s) for s in symbols],
            base_row_version=base_v,
            updated_by=int(operation.get("updated_by") or 0),
        )


_handler = PivotFirmSelectionHandler()
register_handler(_handler)
