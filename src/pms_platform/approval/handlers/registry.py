"""Typed approval handler registry (no dynamic SQL)."""

from __future__ import annotations

from typing import Any, Protocol

from sqlalchemy.orm import Session


class ApprovalHandler(Protocol):
    entity_kind: str

    def validate_operation(self, operation: dict[str, Any]) -> dict[str, Any]:
        """Return validation_result dict; raise on hard failure."""

    def apply_operation(self, session: Session, operation: dict[str, Any]) -> None:
        """Apply one approved operation inside the caller's transaction."""


_REGISTRY: dict[str, ApprovalHandler] = {}


def register_handler(handler: ApprovalHandler) -> None:
    _REGISTRY[handler.entity_kind] = handler


def get_handler(entity_kind: str) -> ApprovalHandler:
    try:
        return _REGISTRY[entity_kind]
    except KeyError as exc:
        raise LookupError(f"no approval handler for {entity_kind}") from exc


def registered_kinds() -> frozenset[str]:
    return frozenset(_REGISTRY)
