"""Copy bhav bars from a legacy snapshot when reconciliation shows they match."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pms_platform.models.nse_bhav import NseBhavBar


@dataclass
class BhavCopyResult:
    source_count: int
    inserted: int
    skipped_existing: int


def copy_bhav_bars(source: Session, target: Session, *, dry_run: bool = False) -> BhavCopyResult:
    """Copy all nse_bhav_bars from source to target (skip duplicates by source_key)."""
    source_bars = list(source.scalars(select(NseBhavBar)).all())
    existing_keys = set(target.scalars(select(NseBhavBar.source_key)).all())
    inserted = 0
    skipped = 0
    for bar in source_bars:
        if bar.source_key in existing_keys:
            skipped += 1
            continue
        inserted += 1
        if not dry_run:
            target.add(
                NseBhavBar(
                    trade_date=bar.trade_date,
                    symbol=bar.symbol,
                    series=bar.series,
                    isin=bar.isin,
                    instrument_name=bar.instrument_name,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    prev_close=bar.prev_close,
                    volume=bar.volume,
                    turnover=bar.turnover,
                    source_key=bar.source_key,
                    run_id=None,
                )
            )
            existing_keys.add(bar.source_key)
    return BhavCopyResult(
        source_count=len(source_bars),
        inserted=inserted,
        skipped_existing=skipped,
    )


def bhav_bar_count(session: Session) -> int:
    return int(session.scalar(select(func.count()).select_from(NseBhavBar)) or 0)
