"""Yahoo Finance quarterly fundamentals fallback provider."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.config import settings
from pms_platform.fundamentals.catalog import CONTRACT_VERSION
from pms_platform.fundamentals.providers.base import ProviderImportResult
from pms_platform.ingestion.common import make_source_key
from pms_platform.market_data.identifiers import IdentifierResolver
from pms_platform.models import ImportBatch, Security
from pms_platform.models.company_fundamentals_quarterly import CompanyFundamentalsQuarterly


@dataclass(frozen=True)
class YahooQuarterlyRow:
    """One Yahoo income-statement quarter."""

    period_end_date: date
    sales: Decimal | None
    ebit: Decimal | None
    pat: Decimal | None


class YahooFundamentalsProvider:
    """Fetch quarterly income statement history from Yahoo quoteSummary."""

    name = "yahoo"

    def __init__(self, *, base_url: str | None = None, timeout: float = 20.0) -> None:
        self._base_url = (base_url or settings.yahoo_finance_base_url).rstrip("/")
        self._timeout = timeout

    def import_data(
        self,
        session: Session,
        *,
        path: Path | None = None,
        tickers: list[tuple[str, str, str | None]] | None = None,
    ) -> ProviderImportResult:
        """Import Yahoo fundamentals for explicit tickers or all resolved securities."""
        targets = tickers or self._default_targets(session)
        if not targets:
            return ProviderImportResult(
                inserted=0, updated=0, skipped=0, invalid=0, import_batch_id=None
            )

        batch = ImportBatch(
            source_type="quarterly_fundamentals",
            source_file=f"yahoo:{self._base_url}",
            source_checksum=f"yahoo-{len(targets)}",
            status="completed",
            notes="Yahoo fundamentals fallback",
        )
        session.add(batch)
        session.flush()

        resolver = IdentifierResolver(session)
        inserted = 0
        updated = 0
        skipped = 0
        invalid = 0
        retrieved_at = datetime.now(timezone.utc)

        for identifier_type, identifier, yahoo_ticker in targets:
            if not yahoo_ticker:
                invalid += 1
                continue
            try:
                quarters = self._fetch_quarters(yahoo_ticker)
            except Exception:
                invalid += 1
                continue

            security_id = None
            resolution = resolver.resolve(identifier_type, identifier, quarter.period_end_date)
            if resolution.status == "RESOLVED":
                security_id = resolution.security_id
            for row_number, quarter in enumerate(quarters, start=1):
                fiscal_year, fiscal_quarter = _fiscal_label(quarter.period_end_date)
                source_key = make_source_key(
                    f"yahoo:{yahoo_ticker}",
                    "yahoo",
                    row_number,
                )
                identity = session.scalar(
                    select(CompanyFundamentalsQuarterly).where(
                        CompanyFundamentalsQuarterly.identifier_type == identifier_type,
                        CompanyFundamentalsQuarterly.identifier == identifier,
                        CompanyFundamentalsQuarterly.period_end_date == quarter.period_end_date,
                        CompanyFundamentalsQuarterly.source == f"YAHOO:{yahoo_ticker}",
                    )
                )
                opm = None
                if quarter.sales and quarter.ebit is not None and quarter.sales != 0:
                    opm = (quarter.ebit / quarter.sales) * Decimal("100")
                npm = None
                if quarter.sales and quarter.pat is not None and quarter.sales != 0:
                    npm = (quarter.pat / quarter.sales) * Decimal("100")

                if identity is not None:
                    identity.sales = quarter.sales
                    identity.ebit = quarter.ebit
                    identity.pat = quarter.pat
                    identity.opm = opm
                    identity.npm = npm
                    identity.security_id = security_id
                    identity.retrieved_at = retrieved_at
                    identity.import_batch_id = batch.import_batch_id
                    updated += 1
                    continue

                session.add(
                    CompanyFundamentalsQuarterly(
                        identifier_type=identifier_type,
                        identifier=identifier,
                        security_id=security_id,
                        fiscal_year=fiscal_year,
                        fiscal_quarter=fiscal_quarter,
                        period_end_date=quarter.period_end_date,
                        sales=quarter.sales,
                        ebit=quarter.ebit,
                        pat=quarter.pat,
                        opm=opm,
                        npm=npm,
                        source=f"YAHOO:{yahoo_ticker}",
                        provider=self.name,
                        contract_version=CONTRACT_VERSION,
                        retrieved_at=retrieved_at,
                        source_file=f"yahoo:{yahoo_ticker}",
                        source_row=row_number,
                        source_key=source_key,
                        import_batch_id=batch.import_batch_id,
                    )
                )
                inserted += 1

        return ProviderImportResult(
            inserted=inserted,
            updated=updated,
            skipped=skipped,
            invalid=invalid,
            import_batch_id=batch.import_batch_id,
        )

    def _default_targets(self, session: Session) -> list[tuple[str, str, str | None]]:
        rows = session.scalars(select(Security)).all()
        targets: list[tuple[str, str, str | None]] = []
        for security in rows:
            ticker = None
            if security.current_nse_symbol:
                ticker = f"{security.current_nse_symbol}.NS"
            elif security.bse_code:
                ticker = f"{security.bse_code}.BO"
            if ticker:
                targets.append(("SECURITY_ID", security.security_id, ticker))
        return targets

    def _fetch_quarters(self, yahoo_ticker: str) -> list[YahooQuarterlyRow]:
        url = (
            f"{self._base_url}/v10/finance/quoteSummary/{yahoo_ticker}"
            "?modules=incomeStatementHistoryQuarterly"
        )
        with httpx.Client(timeout=self._timeout) as client:
            response = client.get(
                url,
                headers={"User-Agent": "pms-platform/1.0"},
            )
            response.raise_for_status()
            payload = response.json()

        result = payload.get("quoteSummary", {}).get("result") or []
        if not result:
            return []
        history = (
            result[0]
            .get("incomeStatementHistoryQuarterly", {})
            .get("incomeStatementHistory", [])
        )
        quarters: list[YahooQuarterlyRow] = []
        for item in history:
            end_raw = (item.get("endDate") or {}).get("fmt")
            if not end_raw:
                continue
            period_end = date.fromisoformat(end_raw)
            quarters.append(
                YahooQuarterlyRow(
                    period_end_date=period_end,
                    sales=_raw_decimal(item.get("totalRevenue", {}).get("raw")),
                    ebit=_raw_decimal(item.get("ebit", {}).get("raw")),
                    pat=_raw_decimal(item.get("netIncome", {}).get("raw")),
                )
            )
        return sorted(quarters, key=lambda row: row.period_end_date)


def _raw_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)) / Decimal("10000000")


def _fiscal_label(period_end: date) -> tuple[int, str]:
    """Map calendar period end to Indian fiscal year/quarter label."""
    month = period_end.month
    if month in {4, 5, 6}:
        quarter = "Q1"
    elif month in {7, 8, 9}:
        quarter = "Q2"
    elif month in {10, 11, 12}:
        quarter = "Q3"
    else:
        quarter = "Q4"
    fiscal_year = period_end.year if month >= 4 else period_end.year - 1
    return fiscal_year, quarter
