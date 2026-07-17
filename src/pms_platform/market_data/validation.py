"""Market-data validation against portfolio snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.market_data.lookup import lookup_daily_price
from pms_platform.models import PortfolioSnapshotRecord, Security


@dataclass(frozen=True)
class PriceSnapshotDiscrepancy:
    """Discrepancy between imported daily close and snapshot CMP."""

    snapshot_date: date
    security_id: str
    portfolio_name: str
    snapshot_price: Decimal
    market_price: Decimal
    market_trade_date: date
    lookup_mode: str
    absolute_difference: Decimal
    relative_difference_pct: Decimal | None


def compare_prices_to_snapshots(
    session: Session,
    *,
    tolerance_pct: Decimal = Decimal("5"),
) -> list[PriceSnapshotDiscrepancy]:
    """Compare daily close prices to snapshot CMP where both exist."""
    snapshots = session.scalars(
        select(PortfolioSnapshotRecord).where(
            PortfolioSnapshotRecord.security_id.is_not(None),
            PortfolioSnapshotRecord.market_price.is_not(None),
        )
    ).all()
    securities = {
        security.security_id: security for security in session.scalars(select(Security)).all()
    }
    discrepancies: list[PriceSnapshotDiscrepancy] = []

    for snapshot in snapshots:
        if snapshot.security_id is None or snapshot.market_price is None:
            continue
        observation = lookup_daily_price(session, snapshot.security_id, snapshot.snapshot_date)
        if observation is None:
            continue

        absolute_difference = abs(observation.close - snapshot.market_price)
        if snapshot.market_price == 0:
            relative_difference_pct = None
            exceeds_tolerance = absolute_difference > 0
        else:
            relative_difference_pct = (absolute_difference / snapshot.market_price) * Decimal("100")
            exceeds_tolerance = relative_difference_pct > tolerance_pct

        if not exceeds_tolerance:
            continue

        security = securities.get(snapshot.security_id)
        discrepancies.append(
            PriceSnapshotDiscrepancy(
                snapshot_date=snapshot.snapshot_date,
                security_id=snapshot.security_id,
                portfolio_name=security.portfolio_name if security else snapshot.portfolio_name,
                snapshot_price=snapshot.market_price,
                market_price=observation.close,
                market_trade_date=observation.trade_date,
                lookup_mode=observation.lookup_mode,
                absolute_difference=absolute_difference,
                relative_difference_pct=relative_difference_pct,
            )
        )

    return discrepancies
