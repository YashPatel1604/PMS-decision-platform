"""Ingest NSE financial filings into quarterly + annual snapshots."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.fundamentals.catalog import CONTRACT_VERSION
from pms_platform.fundamentals.providers.annual_xbrl import upsert_annual_snapshot
from pms_platform.fundamentals.providers.nse.filings import NseFinancialFiling, list_nse_financial_filings
from pms_platform.fundamentals.providers.nse.session import NSESession, NSESessionError
from pms_platform.fundamentals.providers.nse.xbrl import parse_annual_comparative_prior, parse_annual_xbrl, parse_quarterly_xbrl
from pms_platform.ingestion.common import make_source_key
from pms_platform.market_data.bse_financial_results import fiscal_label
from pms_platform.market_data.identifiers import IdentifierResolver
from pms_platform.models import ImportBatch
from pms_platform.models.company_fundamentals_quarterly import CompanyFundamentalsQuarterly

_REQUEST_DELAY_SEC = 0.35
_YEARS_BACK = 8


@dataclass(frozen=True)
class NseTarget:
    nse_symbol: str
    bse_code: str | None = None
    security_id: str | None = None


@dataclass
class NseFinancialsImportResult:
    quarterly_inserted: int = 0
    quarterly_updated: int = 0
    annual_inserted: int = 0
    annual_updated: int = 0
    skipped: int = 0
    failed: int = 0


def _upsert_quarterly(
    session: Session,
    *,
    bse_code: str,
    security_id: str | None,
    batch_id: int,
    filing: NseFinancialFiling,
    facts,
    retrieved_at: datetime,
) -> bool:
    fiscal_year, fiscal_quarter = fiscal_label(facts.period_end)
    source = f"NSE:{filing.symbol}:{filing.source_id}"
    source_key = make_source_key("quarterly_fundamentals", source, facts.period_end.isoformat())
    existing = session.scalar(
        select(CompanyFundamentalsQuarterly).where(
            CompanyFundamentalsQuarterly.source_key == source_key
        )
    )
    fields = dict(
        identifier_type="BSE_CODE",
        identifier=bse_code,
        security_id=security_id,
        fiscal_year=fiscal_year,
        fiscal_quarter=fiscal_quarter,
        period_end_date=facts.period_end,
        sales=facts.sales,
        pat=facts.pat,
        opm=facts.opm,
        npm=facts.npm,
        source=source,
        provider="nse_xbrl",
        contract_version=CONTRACT_VERSION,
        retrieved_at=retrieved_at,
        source_file=filing.xbrl_url,
        source_row=1,
        import_batch_id=batch_id,
    )
    if existing is not None:
        for k, v in fields.items():
            if v is not None or k in {"retrieved_at", "import_batch_id"}:
                setattr(existing, k, v)
        return False
    session.add(CompanyFundamentalsQuarterly(source_key=source_key, **fields))
    return True


def refresh_nse_financials(
    session: Session,
    targets: list[NseTarget],
    *,
    years_back: int = _YEARS_BACK,
    request_delay_sec: float = _REQUEST_DELAY_SEC,
) -> NseFinancialsImportResult:
    """Fetch NSE filings for symbols and upsert quarterly + annual DB rows."""
    if not targets:
        return NseFinancialsImportResult()

    batch = ImportBatch(
        source_type="quarterly_fundamentals",
        source_file="nse:financial-filings",
        source_checksum=f"nse-{len(targets)}",
        status="completed",
        notes="NSE integrated + legacy financial XBRL",
    )
    session.add(batch)
    session.flush()

    resolver = IdentifierResolver(session)
    retrieved_at = datetime.now(timezone.utc)
    result = NseFinancialsImportResult()

    with NSESession() as nse:
        for index, target in enumerate(targets):
            if index > 0:
                time.sleep(request_delay_sec)
            symbol = target.nse_symbol.strip().upper()
            bse_code = (target.bse_code or "").strip()
            if not symbol or not bse_code:
                result.skipped += 1
                continue
            try:
                filings = list_nse_financial_filings(nse, symbol, years_back=years_back)
            except NSESessionError:
                result.failed += 1
                continue
            if not filings:
                result.skipped += 1
                continue

            security_id = target.security_id
            if security_id is None:
                resolution = resolver.resolve("BSE_CODE", bse_code, date.today())
                if resolution.status == "RESOLVED":
                    security_id = resolution.security_id

            seen_annual_years: set[int] = set()

            def _upsert_annual(annual, *, provider: str = "nse_xbrl") -> None:
                nonlocal result
                if annual.fiscal_year in seen_annual_years:
                    return
                seen_annual_years.add(annual.fiscal_year)
                is_new = upsert_annual_snapshot(
                    session,
                    identifier_type="BSE_CODE",
                    identifier=bse_code,
                    security_id=security_id,
                    fiscal_year=annual.fiscal_year,
                    period_end_date=annual.period_end,
                    total_assets=annual.total_assets,
                    total_equity=annual.total_equity,
                    total_debt=annual.total_debt,
                    cash_and_equivalents=annual.cash_and_equivalents,
                    finance_costs=annual.finance_costs,
                    current_assets=annual.current_assets,
                    current_liabilities=annual.current_liabilities,
                    roce=annual.roce,
                    roe=annual.roe,
                    roa=annual.roa,
                    debt_to_equity=annual.debt_to_equity,
                    interest_coverage=annual.interest_coverage,
                    current_ratio=annual.current_ratio,
                    sales=annual.sales,
                    pat=annual.pat,
                    provider=provider,
                )
                if is_new:
                    result.annual_inserted += 1
                else:
                    result.annual_updated += 1

            for filing in filings:
                try:
                    xml_text = nse.get_text(filing.xbrl_url)
                except NSESessionError:
                    continue
                if filing.period_type == "Quarterly":
                    facts = parse_quarterly_xbrl(xml_text, period_end=filing.period_end)
                    if facts is None:
                        continue
                    is_new = _upsert_quarterly(
                        session,
                        bse_code=bse_code,
                        security_id=security_id,
                        batch_id=batch.import_batch_id,
                        filing=filing,
                        facts=facts,
                        retrieved_at=retrieved_at,
                    )
                    if is_new:
                        result.quarterly_inserted += 1
                    else:
                        result.quarterly_updated += 1
                else:
                    # Skip interim/YTD filings mis-tagged as annual — need full-FY (Mar) balance sheets.
                    if filing.period_end.month != 3:
                        continue
                    annual = parse_annual_xbrl(xml_text, period_end=filing.period_end)
                    if annual is None:
                        continue
                    _upsert_annual(annual)
                    prior = parse_annual_comparative_prior(xml_text, period_end=filing.period_end)
                    if prior is not None and (prior.sales is not None or prior.pat is not None):
                        _upsert_annual(prior, provider="nse_xbrl_comparative")

    session.flush()
    return result
