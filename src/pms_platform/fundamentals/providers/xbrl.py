"""BSE quarterly fundamentals provider (TabResults_PAR API)."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.fundamentals.catalog import CONTRACT_VERSION
from pms_platform.fundamentals.providers.base import ProviderImportResult
from pms_platform.ingestion.common import make_source_key
from pms_platform.market_data.bse_http import bse_headers
from pms_platform.market_data.bse_financial_results import (
    BseFinancialResultsFetchError,
    BseResultsSnapshot,
    fetch_bse_results_snapshot,
)
from pms_platform.market_data.bse_xbrl_financial_results import (
    fetch_bse_quarterly_results_with_history,
)
from pms_platform.market_data.bse_scrip_universe import resolve_bse_code
from pms_platform.market_data.identifiers import IdentifierResolver
from pms_platform.models import ImportBatch, Security, WatchlistMember
from pms_platform.models.company_fundamentals_quarterly import CompanyFundamentalsQuarterly

_REQUEST_DELAY_SEC = 0.1
_HISTORY_QUARTERS = 28
_HISTORY_YEARS_BACK = 7
_INTEGRATED_QUARTERS = 4
_FETCH_WORKERS = 4


class XbrlFundamentalsProvider:
    """Fetch quarterly P&L metrics from BSE financial results API."""

    name = "xbrl"

    def __init__(
        self,
        *,
        request_delay_sec: float = _REQUEST_DELAY_SEC,
        max_workers: int = _FETCH_WORKERS,
    ) -> None:
        self._request_delay_sec = request_delay_sec
        self._max_workers = max_workers

    def import_data(
        self,
        session: Session,
        *,
        path: Path | None = None,
        bse_codes: list[str] | None = None,
        include_all_securities: bool = False,
    ) -> ProviderImportResult:
        del path
        targets = self._resolve_targets(
            session,
            bse_codes,
            include_all_securities=include_all_securities,
        )
        if not targets:
            return ProviderImportResult(
                inserted=0, updated=0, skipped=0, invalid=0, import_batch_id=None
            )

        batch = ImportBatch(
            source_type="quarterly_fundamentals",
            source_file="bse:TabResults_PAR",
            source_checksum=f"bse-tabresults-{len(targets)}",
            status="completed",
            notes="BSE TabResults_PAR + financial-results XBRL backfill",
        )
        session.add(batch)
        session.flush()

        resolver = IdentifierResolver(session)
        inserted = 0
        updated = 0
        skipped = 0
        invalid = 0
        retrieved_at = datetime.now(timezone.utc)

        fetched = self._fetch_all_snapshots(targets)

        for original_bse, result in fetched:
            if result is None:
                invalid += 1
                continue
            snapshot, target = result
            if target.bse_code != original_bse:
                self._refresh_member_bse_codes(session, original_bse, target.bse_code)

            if not snapshot.quarters:
                skipped += 1
                continue

            counts = self._upsert_snapshot(
                session,
                snapshot=snapshot,
                target=target,
                batch_id=batch.import_batch_id,
                resolver=resolver,
                retrieved_at=retrieved_at,
            )
            inserted += counts["inserted"]
            updated += counts["updated"]
            skipped += counts["skipped"]

        session.flush()
        return ProviderImportResult(
            inserted=inserted,
            updated=updated,
            skipped=skipped,
            invalid=invalid,
            import_batch_id=batch.import_batch_id,
        )

    def _fetch_all_snapshots(
        self,
        targets: list[_BseTarget],
    ) -> list[tuple[str, tuple[BseResultsSnapshot, _BseTarget] | None]]:
        """Fetch quarterly history for all targets in parallel."""

        def _one(target: _BseTarget) -> tuple[str, tuple[BseResultsSnapshot, _BseTarget] | None]:
            original = target.bse_code
            if self._request_delay_sec > 0:
                time.sleep(self._request_delay_sec)
            try:
                with httpx.Client(
                    headers=bse_headers(),
                    timeout=30.0,
                    follow_redirects=True,
                ) as client:
                    try:
                        client.get("https://www.bseindia.com/")
                    except Exception:
                        pass
                    snapshot, resolved = self._fetch_snapshot(target, client=client)
                    return original, (snapshot, resolved)
            except BseFinancialResultsFetchError:
                return original, None
            except Exception:
                return original, None

        workers = min(self._max_workers, max(1, len(targets)))
        results: list[tuple[str, tuple[BseResultsSnapshot, _BseTarget] | None]] = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_one, t) for t in targets]
            for fut in as_completed(futures):
                results.append(fut.result())
        order = {t.bse_code: i for i, t in enumerate(targets)}
        results.sort(key=lambda item: order.get(item[0], 0))
        return results

    def _fetch_snapshot(
        self,
        target: _BseTarget,
        *,
        client: httpx.Client | None = None,
    ) -> tuple[BseResultsSnapshot, _BseTarget]:
        snapshot = self._fetch_quarters_with_history(target.bse_code, client=client)
        if snapshot.quarters:
            return snapshot, target

        alt_code = resolve_bse_code(
            nse_symbol=target.nse_symbol,
            company_name=target.company_name,
            isin=target.isin,
        )
        if alt_code and alt_code != target.bse_code:
            alt_target = _BseTarget(
                bse_code=alt_code,
                security_id=target.security_id,
                nse_symbol=target.nse_symbol,
                company_name=target.company_name,
                isin=target.isin,
            )
            alt_snapshot = self._fetch_quarters_with_history(alt_code, client=client)
            if alt_snapshot.quarters:
                return alt_snapshot, alt_target
        return snapshot, target

    def _fetch_quarters_with_history(
        self,
        bse_code: str,
        *,
        client: httpx.Client | None = None,
    ) -> BseResultsSnapshot:
        try:
            return fetch_bse_quarterly_results_with_history(
                bse_code,
                max_quarters=_HISTORY_QUARTERS,
                years_back=_HISTORY_YEARS_BACK,
                client=client,
            )
        except BseFinancialResultsFetchError:
            return fetch_bse_results_snapshot(bse_code, client=client)

    def _refresh_member_bse_codes(
        self,
        session: Session,
        old_code: str,
        new_code: str,
    ) -> None:
        members = session.scalars(
            select(WatchlistMember).where(WatchlistMember.bse_code == old_code)
        ).all()
        for member in members:
            member.bse_code = new_code

    def _upsert_snapshot(
        self,
        session: Session,
        *,
        snapshot: BseResultsSnapshot,
        target: _BseTarget,
        batch_id: int,
        resolver: IdentifierResolver,
        retrieved_at: datetime,
    ) -> dict[str, int]:
        inserted = 0
        updated = 0
        skipped = 0

        identifier_type = "BSE_CODE"
        identifier = target.bse_code
        security_id = target.security_id
        if security_id is None:
            resolution = resolver.resolve(identifier_type, identifier, date.today())
            if resolution.status == "RESOLVED":
                security_id = resolution.security_id

        for row_number, quarter in enumerate(snapshot.quarters, start=1):
            if quarter.sales is None and quarter.pat is None:
                skipped += 1
                continue

            ebit = None
            if quarter.sales is not None and quarter.opm is not None:
                ebit = (quarter.sales * quarter.opm) / Decimal("100")

            source = f"BSE:{snapshot.bse_code}"
            source_key = make_source_key(
                f"bse:{snapshot.bse_code}",
                quarter.period_label,
                row_number,
            )
            identity = session.scalar(
                select(CompanyFundamentalsQuarterly).where(
                    CompanyFundamentalsQuarterly.identifier_type == identifier_type,
                    CompanyFundamentalsQuarterly.identifier == identifier,
                    CompanyFundamentalsQuarterly.period_end_date == quarter.period_end_date,
                    CompanyFundamentalsQuarterly.source == source,
                )
            )
            if identity is None:
                identity = session.scalar(
                    select(CompanyFundamentalsQuarterly).where(
                        CompanyFundamentalsQuarterly.source_key == source_key
                    )
                )

            if identity is not None:
                identity.sales = quarter.sales
                identity.pat = quarter.pat
                identity.opm = quarter.opm
                identity.npm = quarter.npm
                identity.ebit = ebit
                identity.security_id = security_id
                identity.fiscal_year = quarter.fiscal_year
                identity.fiscal_quarter = quarter.fiscal_quarter
                identity.period_end_date = quarter.period_end_date
                identity.source = source
                identity.source_key = source_key
                identity.retrieved_at = retrieved_at
                identity.import_batch_id = batch_id
                updated += 1
                continue

            session.add(
                CompanyFundamentalsQuarterly(
                    identifier_type=identifier_type,
                    identifier=identifier,
                    security_id=security_id,
                    fiscal_year=quarter.fiscal_year,
                    fiscal_quarter=quarter.fiscal_quarter,
                    period_end_date=quarter.period_end_date,
                    sales=quarter.sales,
                    ebit=ebit,
                    pat=quarter.pat,
                    opm=quarter.opm,
                    npm=quarter.npm,
                    source=source,
                    provider=self.name,
                    contract_version=CONTRACT_VERSION,
                    retrieved_at=retrieved_at,
                    source_file=f"bse:TabResults_PAR:{snapshot.bse_code}",
                    source_row=row_number,
                    source_key=source_key,
                    import_batch_id=batch_id,
                )
            )
            inserted += 1

        return {"inserted": inserted, "updated": updated, "skipped": skipped}

    def _resolve_targets(
        self,
        session: Session,
        bse_codes: list[str] | None,
        *,
        include_all_securities: bool = False,
    ) -> list[_BseTarget]:
        if bse_codes:
            codes = sorted({code.strip() for code in bse_codes if code and code.strip()})
            return [
                _BseTarget(bse_code=code, security_id=None)
                for code in codes
            ]

        seen: set[str] = set()
        targets: list[_BseTarget] = []

        members = session.scalars(
            select(WatchlistMember).where(WatchlistMember.bse_code.is_not(None))
        ).all()
        for member in members:
            code = member.bse_code.strip()
            if not code or code in seen:
                continue
            seen.add(code)
            targets.append(
                _BseTarget(
                    bse_code=code,
                    security_id=member.security_id,
                    nse_symbol=member.nse_symbol,
                    company_name=member.display_name,
                    isin=member.isin,
                )
            )

        if include_all_securities:
            securities = session.scalars(
                select(Security).where(Security.bse_code.is_not(None))
            ).all()
            for security in securities:
                code = (security.bse_code or "").strip()
                if not code or code in seen:
                    continue
                seen.add(code)
                targets.append(
                    _BseTarget(
                        bse_code=code,
                        security_id=security.security_id,
                        nse_symbol=security.current_nse_symbol,
                        company_name=security.canonical_name or security.portfolio_name,
                        isin=security.isin,
                    )
                )

        return targets


class _BseTarget:
    """One BSE scrip to fetch fundamentals for."""

    __slots__ = ("bse_code", "security_id", "nse_symbol", "company_name", "isin")

    def __init__(
        self,
        *,
        bse_code: str,
        security_id: str | None,
        nse_symbol: str | None = None,
        company_name: str | None = None,
        isin: str | None = None,
    ) -> None:
        self.bse_code = bse_code
        self.security_id = security_id
        self.nse_symbol = nse_symbol
        self.company_name = company_name
        self.isin = isin
