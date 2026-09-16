"""Price and benchmark lookup helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from pms_platform.models import BenchmarkTri, DailyPrice

_LIVE_SOURCES = frozenset({"YAHOO_FINANCE", "INDIAN_STOCK_API"})

# Prefer rights-aware Yahoo repair over older EOD2 rows when both exist for a date.
# Alphabetical source order alone would pick EOD2_* over YAHOO_CHART_REPAIR.
_SOURCE_PRIORITY = case(
    (DailyPrice.source == "YAHOO_CHART_REPAIR", 0),
    (DailyPrice.source.in_(_LIVE_SOURCES), 1),
    else_=2,
)


@dataclass(frozen=True)
class PriceObservation:
    """Resolved price observation for a security on a lookup date."""

    security_id: str
    requested_date: date
    trade_date: date
    close: Decimal
    adjusted_close: Decimal
    lookup_mode: str


@dataclass(frozen=True)
class BenchmarkObservation:
    """Resolved benchmark TRI observation for a lookup date."""

    benchmark_code: str
    requested_date: date
    trade_date: date
    tri_level: Decimal
    lookup_mode: str


def lookup_daily_price(
    session: Session,
    security_id: str,
    as_of_date: date,
    *,
    allow_live: bool = True,
) -> PriceObservation | None:
    """Return the exact-date or prior-trading-day price for a security.

    When ``allow_live`` is False, Yahoo / live API marks are ignored so
    Current Holdings stay on Excel/EOD book prices only.
    """
    exact_query = select(DailyPrice).where(
        DailyPrice.security_id == security_id,
        DailyPrice.trade_date == as_of_date,
    )
    if not allow_live:
        exact_query = exact_query.where(DailyPrice.source.not_in(_LIVE_SOURCES))
    # scalar() does not add LIMIT; without it Postgres ships every matching row.
    exact = session.scalar(
        exact_query.order_by(_SOURCE_PRIORITY, DailyPrice.source).limit(1)
    )
    if exact is not None:
        return PriceObservation(
            security_id=security_id,
            requested_date=as_of_date,
            trade_date=exact.trade_date,
            close=exact.close,
            adjusted_close=exact.adjusted_close,
            lookup_mode="EXACT",
        )

    prior_query = select(DailyPrice).where(
        DailyPrice.security_id == security_id,
        DailyPrice.trade_date < as_of_date,
    )
    if not allow_live:
        prior_query = prior_query.where(DailyPrice.source.not_in(_LIVE_SOURCES))
    prior = session.scalar(
        prior_query.order_by(
            DailyPrice.trade_date.desc(),
            _SOURCE_PRIORITY,
            DailyPrice.source,
        ).limit(1)
    )
    if prior is None:
        return None
    return PriceObservation(
        security_id=security_id,
        requested_date=as_of_date,
        trade_date=prior.trade_date,
        close=prior.close,
        adjusted_close=prior.adjusted_close,
        lookup_mode="PRIOR_TRADING_DAY",
    )


def lookup_benchmark_tri(
    session: Session,
    benchmark_code: str,
    as_of_date: date,
) -> BenchmarkObservation | None:
    """Return the exact-date or prior-trading-day TRI level for a benchmark."""
    normalized_code = benchmark_code.strip().upper()
    exact = session.scalar(
        select(BenchmarkTri)
        .where(
            BenchmarkTri.benchmark_code == normalized_code,
            BenchmarkTri.trade_date == as_of_date,
        )
        .order_by(BenchmarkTri.source)
        .limit(1)
    )
    if exact is not None:
        return BenchmarkObservation(
            benchmark_code=normalized_code,
            requested_date=as_of_date,
            trade_date=exact.trade_date,
            tri_level=exact.tri_level,
            lookup_mode="EXACT",
        )

    prior = session.scalar(
        select(BenchmarkTri)
        .where(
            BenchmarkTri.benchmark_code == normalized_code,
            BenchmarkTri.trade_date < as_of_date,
        )
        .order_by(BenchmarkTri.trade_date.desc(), BenchmarkTri.source)
        .limit(1)
    )
    if prior is None:
        return None
    return BenchmarkObservation(
        benchmark_code=normalized_code,
        requested_date=as_of_date,
        trade_date=prior.trade_date,
        tri_level=prior.tri_level,
        lookup_mode="PRIOR_TRADING_DAY",
    )
