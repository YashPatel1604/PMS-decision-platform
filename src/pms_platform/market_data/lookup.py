"""Price and benchmark lookup helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from pms_platform.models import BenchmarkTri, DailyPrice

_LIVE_SOURCES = frozenset({"YAHOO_FINANCE", "INDIAN_STOCK_API"})


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
) -> PriceObservation | None:
    """Return the exact-date or prior-trading-day price for a security."""
    exact = session.scalar(
        select(DailyPrice)
        .where(
            DailyPrice.security_id == security_id,
            DailyPrice.trade_date == as_of_date,
        )
        .order_by(
            case((DailyPrice.source.in_(_LIVE_SOURCES), 0), else_=1),
            DailyPrice.source,
        )
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

    prior = session.scalar(
        select(DailyPrice)
        .where(
            DailyPrice.security_id == security_id,
            DailyPrice.trade_date < as_of_date,
        )
        .order_by(DailyPrice.trade_date.desc(), DailyPrice.source)
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
