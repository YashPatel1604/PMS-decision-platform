"""Benchmark period-return helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from pms_platform.market_data.contracts import REQUIRED_BENCHMARKS
from pms_platform.market_data.lookup import lookup_benchmark_tri

_DAYS_PER_YEAR = Decimal("365")
_HUNDRED = Decimal("100")
_ZERO = Decimal("0")
_ONE = Decimal("1")


@dataclass(frozen=True)
class BenchmarkPeriodReturn:
    """Benchmark index return over a date window."""

    benchmark_code: str
    start_date: date
    end_date: date
    start_level: Decimal
    end_level: Decimal
    start_lookup_mode: str
    end_lookup_mode: str
    total_return_pct: Decimal
    annualized_return_pct: Decimal | None


def primary_benchmark_code() -> str:
    """Return the configured primary small-cap benchmark code."""
    return REQUIRED_BENCHMARKS[0]


def compute_benchmark_period_return(
    session: Session,
    *,
    benchmark_code: str,
    start_date: date,
    end_date: date,
) -> BenchmarkPeriodReturn | None:
    """Compute price-index return between two episode-aligned dates."""
    start_observation = lookup_benchmark_tri(session, benchmark_code, start_date)
    end_observation = lookup_benchmark_tri(session, benchmark_code, end_date)
    if start_observation is None or end_observation is None:
        return None
    if start_observation.tri_level <= 0:
        return None

    total_return = (
        (end_observation.tri_level / start_observation.tri_level) - _ONE
    ) * _HUNDRED
    holding_days = (end_observation.trade_date - start_observation.trade_date).days
    annualized: Decimal | None
    if holding_days <= 0:
        annualized = None
    else:
        growth = _ONE + (total_return / _HUNDRED)
        exponent = _DAYS_PER_YEAR / Decimal(holding_days)
        annualized = ((growth**exponent) - _ONE) * _HUNDRED

    return BenchmarkPeriodReturn(
        benchmark_code=benchmark_code,
        start_date=start_observation.trade_date,
        end_date=end_observation.trade_date,
        start_level=start_observation.tri_level,
        end_level=end_observation.tri_level,
        start_lookup_mode=start_observation.lookup_mode,
        end_lookup_mode=end_observation.lookup_mode,
        total_return_pct=total_return,
        annualized_return_pct=annualized,
    )
