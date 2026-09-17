"""Versioned investment thesis helpers."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pms_platform.models.investment_thesis import InvestmentThesis

_ALLOWED_STATUS = frozenset({"draft", "active", "superseded", "archived"})

_THESIS_FIELDS = (
    "thesis_summary",
    "business_quality",
    "industry_thesis",
    "competitive_advantage",
    "management_thesis",
    "capital_allocation_thesis",
    "revenue_assumption",
    "margin_assumption",
    "earnings_assumption",
    "valuation_framework",
    "expected_holding_period",
    "bull_case",
    "base_case",
    "bear_case",
    "key_risks",
    "key_monitoring_variables",
    "disconfirming_evidence",
)


def list_theses(
    session: Session,
    *,
    security_id: str | None = None,
    active_only: bool = True,
) -> list[InvestmentThesis]:
    stmt = select(InvestmentThesis).order_by(
        InvestmentThesis.security_id, InvestmentThesis.version.desc()
    )
    if security_id:
        stmt = stmt.where(InvestmentThesis.security_id == security_id)
    if active_only:
        stmt = stmt.where(InvestmentThesis.status == "active")
    return list(session.scalars(stmt).all())


def get_active_thesis(session: Session, security_id: str) -> InvestmentThesis | None:
    return session.scalar(
        select(InvestmentThesis)
        .where(
            InvestmentThesis.security_id == security_id,
            InvestmentThesis.status == "active",
        )
        .order_by(InvestmentThesis.version.desc())
        .limit(1)
    )


def create_thesis(
    session: Session,
    *,
    security_id: str,
    created_by: str | None = None,
    status: str = "active",
    **fields: str | None,
) -> InvestmentThesis:
    cleaned = (status or "active").strip().lower()
    if cleaned not in _ALLOWED_STATUS:
        raise ValueError(f"status must be one of {sorted(_ALLOWED_STATUS)}")

    next_version = (
        session.scalar(
            select(func.coalesce(func.max(InvestmentThesis.version), 0)).where(
                InvestmentThesis.security_id == security_id
            )
        )
        or 0
    ) + 1

    if cleaned == "active":
        for prior in session.scalars(
            select(InvestmentThesis).where(
                InvestmentThesis.security_id == security_id,
                InvestmentThesis.status == "active",
            )
        ).all():
            prior.status = "superseded"

    payload = {key: fields.get(key) for key in _THESIS_FIELDS}
    row = InvestmentThesis(
        security_id=security_id,
        version=next_version,
        status=cleaned,
        created_by=created_by,
        **payload,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def revise_thesis(
    session: Session,
    thesis_id: int,
    *,
    created_by: str | None = None,
    **fields: str | None,
) -> InvestmentThesis:
    """Create a new version from an existing thesis (never mutates history)."""
    current = session.get(InvestmentThesis, thesis_id)
    if current is None:
        raise ValueError("thesis not found")
    merged = {key: getattr(current, key) for key in _THESIS_FIELDS}
    for key, value in fields.items():
        if key in _THESIS_FIELDS and value is not None:
            merged[key] = value
    return create_thesis(
        session,
        security_id=current.security_id,
        created_by=created_by,
        status="active",
        **merged,
    )
