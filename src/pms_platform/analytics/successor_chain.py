"""Successor-security resolution for post-exit price lookup."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.models import SecuritySuccessor


def resolve_price_security_id(session: Session, security_id: str, as_of_date: date) -> str:
    """Return the security ID whose price series should be used on a date."""
    current = security_id
    seen: set[str] = {current}
    while True:
        successor = session.scalar(
            select(SecuritySuccessor)
            .where(
                SecuritySuccessor.predecessor_security_id == current,
                SecuritySuccessor.effective_date <= as_of_date,
                SecuritySuccessor.confirmed.is_(True),
            )
            .order_by(
                SecuritySuccessor.effective_date.desc(),
                SecuritySuccessor.successor_id.desc(),
            )
        )
        if successor is None or successor.successor_security_id in seen:
            return current
        seen.add(successor.successor_security_id)
        current = successor.successor_security_id
