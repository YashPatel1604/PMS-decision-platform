"""Compute price return metrics from daily_prices table."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.market_data.identifiers import IdentifierResolver
from pms_platform.models.daily_price import DailyPrice
from pms_platform.models.valuation_snapshot import ValuationSnapshot

_HUNDRED = Decimal("100")


@dataclass(frozen=True)
class PriceReturnResult:
    """Computed price return metrics for one identifier."""

    identifier_type: str
    identifier: str
    return_1m_pct: Decimal | None
    return_3m_pct: Decimal | None
    return_6m_pct: Decimal | None
    return_1y_pct: Decimal | None
    return_3y_pct: Decimal | None
    all_time_high: Decimal | None
    week_52_high: Decimal | None
    week_52_low: Decimal | None
    latest_date: date | None
    latest_close: Decimal | None


def _pct_return(current: Decimal, prior: Decimal) -> Decimal | None:
    if prior == 0:
        return None
    return ((current - prior) / prior * _HUNDRED).quantize(Decimal("0.0001"))


def compute_price_returns(
    prices: list[DailyPrice],
    *,
    reference_date: date | None = None,
) -> PriceReturnResult | None:
    """Compute return metrics from a sorted list of DailyPrice rows.

    Rows must all share the same (identifier_type, identifier).
    """
    if not prices:
        return None

    identifier_type = prices[0].identifier_type
    identifier = prices[0].identifier
    ref = reference_date or date.today()

    sorted_prices = sorted(prices, key=lambda p: p.trade_date)
    latest = sorted_prices[-1]
    current_close = latest.adjusted_close
    all_time_high: Decimal = max(p.close for p in sorted_prices)

    def closest_close(lookback_days: int) -> Decimal | None:
        target = ref - timedelta(days=lookback_days)
        candidates = [p for p in sorted_prices if p.trade_date <= target]
        if not candidates:
            return None
        return candidates[-1].adjusted_close

    # ponytail: calendar 365d window, not exact 252 sessions — good enough for screener.
    week_cut = ref - timedelta(days=365)
    week_closes = [p.close for p in sorted_prices if p.trade_date >= week_cut]
    week_52_high = max(week_closes) if week_closes else None
    week_52_low = min(week_closes) if week_closes else None

    return PriceReturnResult(
        identifier_type=identifier_type,
        identifier=identifier,
        return_1m_pct=_pct_return(current_close, c) if (c := closest_close(31)) else None,
        return_3m_pct=_pct_return(current_close, c) if (c := closest_close(92)) else None,
        return_6m_pct=_pct_return(current_close, c) if (c := closest_close(184)) else None,
        return_1y_pct=_pct_return(current_close, c) if (c := closest_close(365)) else None,
        return_3y_pct=_pct_return(current_close, c) if (c := closest_close(365 * 3)) else None,
        all_time_high=all_time_high,
        week_52_high=week_52_high,
        week_52_low=week_52_low,
        latest_date=latest.trade_date,
        latest_close=current_close,
    )


def _load_daily_prices(
    session: Session,
    identifier_type: str,
    identifier: str,
    *,
    as_of: date,
) -> list[DailyPrice]:
    """Load price history; BSE_CODE maps through security_id (seed uses SECURITY_ID)."""
    prices = list(
        session.scalars(
            select(DailyPrice)
            .where(
                DailyPrice.identifier_type == identifier_type,
                DailyPrice.identifier == identifier,
            )
            .order_by(DailyPrice.trade_date)
        ).all()
    )
    if prices:
        return prices

    if identifier_type.upper() != "BSE_CODE":
        return []

    security_id: str | None = None
    resolution = IdentifierResolver(session).resolve("BSE_CODE", identifier, as_of)
    if resolution.status == "RESOLVED" and resolution.security_id:
        security_id = resolution.security_id
    if security_id is None:
        from pms_platform.models import Security
        from pms_platform.models.watchlist import WatchlistMember

        security_id = session.scalar(
            select(Security.security_id).where(Security.bse_code == identifier)
        )
        if security_id is None:
            security_id = session.scalar(
                select(WatchlistMember.security_id).where(
                    WatchlistMember.bse_code == identifier,
                    WatchlistMember.security_id.isnot(None),
                )
            )
    if not security_id:
        return []

    return list(
        session.scalars(
            select(DailyPrice)
            .where(DailyPrice.security_id == security_id)
            .order_by(DailyPrice.trade_date)
        ).all()
    )


def refresh_price_returns(
    session: Session,
    identifier_pairs: list[tuple[str, str]],
    *,
    reference_date: date | None = None,
) -> dict[tuple[str, str], PriceReturnResult]:
    """Compute price returns for each (identifier_type, identifier) and merge into valuation_snapshots."""
    if not identifier_pairs:
        return {}

    ref = reference_date or date.today()
    results: dict[tuple[str, str], PriceReturnResult] = {}

    for identifier_type, identifier in identifier_pairs:
        prices = _load_daily_prices(session, identifier_type, identifier, as_of=ref)
        result = compute_price_returns(prices, reference_date=ref)
        if result is None:
            continue

        # Keep screener key as the requested identifier (usually BSE_CODE).
        result = PriceReturnResult(
            identifier_type=identifier_type,
            identifier=identifier,
            return_1m_pct=result.return_1m_pct,
            return_3m_pct=result.return_3m_pct,
            return_6m_pct=result.return_6m_pct,
            return_1y_pct=result.return_1y_pct,
            return_3y_pct=result.return_3y_pct,
            all_time_high=result.all_time_high,
            week_52_high=result.week_52_high,
            week_52_low=result.week_52_low,
            latest_date=result.latest_date,
            latest_close=result.latest_close,
        )
        results[(identifier_type, identifier)] = result

        existing = session.scalar(
            select(ValuationSnapshot).where(
                ValuationSnapshot.identifier_type == identifier_type,
                ValuationSnapshot.identifier == identifier,
                ValuationSnapshot.as_of_date == ref,
            )
        )
        updates = dict(
            return_1m_pct=result.return_1m_pct,
            return_3m_pct=result.return_3m_pct,
            return_6m_pct=result.return_6m_pct,
            return_1y_pct=result.return_1y_pct,
            return_3y_pct=result.return_3y_pct,
            all_time_high=result.all_time_high,
            week_52_high=result.week_52_high,
            week_52_low=result.week_52_low,
        )
        if existing is not None:
            for key, value in updates.items():
                if value is not None:
                    setattr(existing, key, value)
        else:
            session.add(
                ValuationSnapshot(
                    identifier_type=identifier_type,
                    identifier=identifier,
                    as_of_date=ref,
                    provider="price_history",
                    **updates,
                )
            )

    session.flush()
    return results
