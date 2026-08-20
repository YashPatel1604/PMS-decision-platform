"""Promoter shareholding snapshot provider."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.market_data.bse_http import bse_headers as _bse_headers
from pms_platform.market_data.bse_shareholding import (
    BseShareholdingSnapshot,
    fetch_bse_shareholding,
)
from pms_platform.market_data.identifiers import IdentifierResolver
from pms_platform.models.promoter_snapshot import PromoterSnapshot

_REQUEST_DELAY_SEC = 0.1
_FETCH_WORKERS = 4


@dataclass
class PromoterImportResult:
    inserted: int
    updated: int
    skipped: int


def _upsert_promoter_snapshot(
    session: Session,
    *,
    identifier_type: str,
    identifier: str,
    security_id: str | None,
    quarter_end_date: date,
    promoter_holding_pct: Decimal | None,
    pledged_pct: Decimal | None,
    prior_holding_pct: Decimal | None,
    provider: str = "bse_shareholding",
) -> bool:
    """Insert or update a PromoterSnapshot; returns True if new row."""
    change_pp: Decimal | None = None
    if promoter_holding_pct is not None and prior_holding_pct is not None:
        change_pp = (promoter_holding_pct - prior_holding_pct).quantize(Decimal("0.0001"))

    existing = session.scalar(
        select(PromoterSnapshot).where(
            PromoterSnapshot.identifier_type == identifier_type,
            PromoterSnapshot.identifier == identifier,
            PromoterSnapshot.quarter_end_date == quarter_end_date,
        )
    )
    if existing is not None:
        existing.security_id = security_id
        existing.promoter_holding_pct = promoter_holding_pct
        existing.promoter_holding_change_pp = change_pp
        existing.pledged_pct = pledged_pct
        existing.computed_at = datetime.now(timezone.utc)
        return False

    session.add(
        PromoterSnapshot(
            identifier_type=identifier_type,
            identifier=identifier,
            security_id=security_id,
            quarter_end_date=quarter_end_date,
            promoter_holding_pct=promoter_holding_pct,
            promoter_holding_change_pp=change_pp,
            pledged_pct=pledged_pct,
            provider=provider,
        )
    )
    return True


def _fetch_shareholding_parallel(
    bse_codes: list[str],
    *,
    max_workers: int,
) -> dict[str, BseShareholdingSnapshot | None]:
    def _one(code: str) -> tuple[str, BseShareholdingSnapshot | None]:
        with httpx.Client(headers=_bse_headers(), follow_redirects=True) as client:
            return code, fetch_bse_shareholding(code, client=client)

    results: dict[str, BseShareholdingSnapshot | None] = {}
    workers = min(max_workers, max(1, len(bse_codes)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_one, code) for code in bse_codes]
        for fut in as_completed(futures):
            code, snap = fut.result()
            results[code] = snap
    return results


def refresh_promoter_snapshots(
    session: Session,
    bse_codes: list[str],
    *,
    request_delay_sec: float = _REQUEST_DELAY_SEC,
    max_workers: int = _FETCH_WORKERS,
) -> PromoterImportResult:
    """Fetch BSE shareholding patterns and upsert PromoterSnapshot rows."""
    del request_delay_sec
    resolver = IdentifierResolver(session)
    today = date.today()
    inserted = 0
    updated = 0
    skipped = 0

    snaps = _fetch_shareholding_parallel(bse_codes, max_workers=max_workers)

    for bse_code in bse_codes:
        snap = snaps.get(bse_code)
        if snap is None:
            skipped += 1
            continue

        resolution = resolver.resolve("BSE_CODE", bse_code, today)
        security_id = resolution.security_id if resolution.status == "RESOLVED" else None

        prior = session.scalar(
            select(PromoterSnapshot)
            .where(
                PromoterSnapshot.identifier_type == "BSE_CODE",
                PromoterSnapshot.identifier == bse_code,
                PromoterSnapshot.quarter_end_date < snap.quarter_end_date,
            )
            .order_by(PromoterSnapshot.quarter_end_date.desc())
        )
        prior_pct = prior.promoter_holding_pct if prior else None

        is_new = _upsert_promoter_snapshot(
            session,
            identifier_type="BSE_CODE",
            identifier=bse_code,
            security_id=security_id,
            quarter_end_date=snap.quarter_end_date,
            promoter_holding_pct=snap.promoter_holding_pct,
            pledged_pct=snap.pledged_pct,
            prior_holding_pct=prior_pct,
        )
        if is_new:
            inserted += 1
        else:
            updated += 1

    session.flush()
    return PromoterImportResult(inserted=inserted, updated=updated, skipped=skipped)
