"""Deep annual FY history backfill for 5Y CAGR endpoints (not quarterly crawl)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date

from sqlalchemy import distinct, select
from sqlalchemy.orm import Session

from pms_platform.fundamentals.annual_cagr import missing_fiscal_years_for_5y, required_cagr_period_ends
from pms_platform.fundamentals.providers.annual_xbrl import refresh_annual_fundamentals
from pms_platform.fundamentals.providers.nse import NseTarget, refresh_nse_financials
from pms_platform.market_data.bse_financial_results import fiscal_label
from pms_platform.models.company_fundamentals_quarterly import CompanyFundamentalsQuarterly
from pms_platform.models.watchlist import WatchlistMember
from pms_platform.watchlists.financial_discovery import build_financial_discovery_identities
from pms_platform.watchlists.identity_link import is_canonically_linked
from pms_platform.watchlists.metric_diagnostics import bse_code


@dataclass
class AnnualHistoryBackfillResult:
    securities_processed: int = 0
    nse_codes: int = 0
    annual_rows_inserted: int = 0
    errors: list[str] | None = None


def _hydrate_annual_from_quarterly(session: Session, bse_code: str, fiscal_year: int) -> bool:
    """Copy Q4 sales/PAT into annual snapshot when annual row exists without P&L."""
    from pms_platform.fundamentals.annual_cagr import _q4_fallback
    from pms_platform.fundamentals.providers.annual_xbrl import upsert_annual_snapshot
    from pms_platform.models.annual_fundamentals_snapshot import AnnualFundamentalsSnapshot

    q_row = session.scalar(
        select(CompanyFundamentalsQuarterly)
        .where(
            CompanyFundamentalsQuarterly.identifier_type == "BSE_CODE",
            CompanyFundamentalsQuarterly.identifier == bse_code,
            CompanyFundamentalsQuarterly.fiscal_year == fiscal_year,
        )
        .order_by(CompanyFundamentalsQuarterly.period_end_date.desc())
        .limit(1)
    )
    row = session.scalar(
        select(AnnualFundamentalsSnapshot).where(
            AnnualFundamentalsSnapshot.identifier_type == "BSE_CODE",
            AnnualFundamentalsSnapshot.identifier == bse_code,
            AnnualFundamentalsSnapshot.fiscal_year == fiscal_year,
        )
    )
    q_sales, q_pat = _q4_fallback(session, bse_code, fiscal_year=fiscal_year)
    if q_sales is None and q_pat is None:
        return False
    if row is not None:
        changed = False
        if row.sales is None and q_sales is not None:
            row.sales = q_sales
            changed = True
        if row.pat is None and q_pat is not None:
            row.pat = q_pat
            changed = True
        return changed

    period_end = q_row.period_end_date if q_row and q_row.period_end_date else date(fiscal_year + 1, 3, 31)
    upsert_annual_snapshot(
        session,
        identifier_type="BSE_CODE",
        identifier=bse_code,
        security_id=None,
        fiscal_year=fiscal_year,
        period_end_date=period_end,
        sales=q_sales,
        pat=q_pat,
        total_assets=None,
        total_equity=None,
        total_debt=None,
        cash_and_equivalents=None,
        finance_costs=None,
        current_assets=None,
        current_liabilities=None,
        roce=None,
        roe=None,
        roa=None,
        debt_to_equity=None,
        interest_coverage=None,
        current_ratio=None,
        provider="quarterly_q4_derived",
    )
    session.flush()
    return True


def refresh_annual_history_for_bse(
    session: Session,
    *,
    bse_code: str,
    nse_symbol: str | None,
    security_id: str | None,
    nse_symbols: tuple[str, ...] = (),
    bse_codes: tuple[str, ...] = (),
    years_back: int = 10,
    request_delay_sec: float = 0.35,
    hydrate_only: bool = False,
) -> tuple[int, list[str]]:
    """Fetch missing annual FY endpoints via NSE annual + BSE annual + Q4 hydrate."""
    errors: list[str] = []
    inserted = 0
    all_nse = tuple(dict.fromkeys([s for s in (nse_symbol, *nse_symbols) if s]))
    all_bse = tuple(dict.fromkeys([c for c in (bse_code, *bse_codes) if c]))

    if not hydrate_only:
        missing = missing_fiscal_years_for_5y(session, bse_code, years_back=years_back)
        if not missing:
            for fy in date_fy_range(session, bse_code, years_back):
                _hydrate_annual_from_quarterly(session, bse_code, fy)

        for sym in all_nse:
            try:
                result = refresh_nse_financials(
                    session,
                    [NseTarget(nse_symbol=sym, bse_code=bse_code, security_id=security_id)],
                    years_back=years_back,
                    request_delay_sec=request_delay_sec,
                )
                inserted += result.annual_inserted
            except Exception as exc:  # noqa: BLE001
                errors.append(f"NSE annual {sym}/{bse_code}: {exc}")
            time.sleep(request_delay_sec)

        for code in all_bse:
            try:
                bse_result = refresh_annual_fundamentals(
                    session,
                    [code],
                    years_back=years_back,
                    request_delay_sec=0.2,
                )
                inserted += bse_result.inserted
            except Exception as exc:  # noqa: BLE001
                errors.append(f"BSE annual {code}: {exc}")

    hydrate_fys: set[int] = set(missing_fiscal_years_for_5y(session, bse_code, years_back=years_back))
    latest_pe, base_pe = required_cagr_period_ends(session, bse_code, extra_bse_codes=bse_codes)
    for pe in (latest_pe, base_pe):
        if pe is not None:
            fy, _ = fiscal_label(pe)
            hydrate_fys.add(fy)
    q_fys = session.scalars(
        select(distinct(CompanyFundamentalsQuarterly.fiscal_year)).where(
            CompanyFundamentalsQuarterly.identifier_type == "BSE_CODE",
            CompanyFundamentalsQuarterly.identifier == bse_code,
        )
    ).all()
    hydrate_fys.update(int(fy) for fy in q_fys)
    for fy in sorted(hydrate_fys):
        if _hydrate_annual_from_quarterly(session, bse_code, fy):
            inserted += 1

    return inserted, errors


def date_fy_range(session: Session, bse_code: str, years_back: int) -> range:
    from pms_platform.fundamentals.annual_cagr import _annual_rows

    rows = _annual_rows(session, bse_code)
    if not rows:
        return range(0)
    latest = max(r.fiscal_year for r in rows)
    return range(latest - years_back, latest + 1)


def refresh_alias_financial_history(session: Session) -> AnnualHistoryBackfillResult:
    """Backfill pre-rename NSE/BSE identities for verified RENAMED aliases."""
    from pms_platform.watchlists.identity_aliases import historical_discovery_targets

    result = AnnualHistoryBackfillResult(errors=[])
    targets = historical_discovery_targets(session)
    for target in targets:
        try:
            nse_syms = tuple(s for s in (target.historical_nse,) if s)
            bse_codes = tuple(dict.fromkeys(c for c in (target.historical_bse, target.canonical_bse) if c))
            n, errs = refresh_annual_history_for_bse(
                session,
                bse_code=target.canonical_bse,
                nse_symbol=target.canonical_nse,
                security_id=target.security_id,
                nse_symbols=nse_syms,
                bse_codes=bse_codes,
                years_back=10,
            )
            result.annual_rows_inserted += n
            assert result.errors is not None
            result.errors.extend(errs)
            result.securities_processed += 1
            session.commit()
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            assert result.errors is not None
            result.errors.append(f"alias {target.watchlist_name}: {exc}")
        time.sleep(0.35)
    return result


def refresh_watchlist_annual_history(
    session: Session,
    *,
    watchlist_id: int | None = None,
    security_id: str | None = None,
    years_back: int = 10,
) -> AnnualHistoryBackfillResult:
    """Deep annual backfill for linked watchlist members needing 5Y CAGR."""
    q = select(WatchlistMember)
    if watchlist_id is not None:
        q = q.where(WatchlistMember.watchlist_id == watchlist_id)
    if security_id:
        q = q.where(WatchlistMember.security_id == security_id)
    members = list(session.scalars(q).all())
    result = AnnualHistoryBackfillResult(errors=[])

    for member in members:
        if not is_canonically_linked(member):
            continue
        bse = bse_code(member)
        if not bse:
            continue
        nse = member.nse_symbol
        nse_symbols: tuple[str, ...] = ()
        hist_bse: tuple[str, ...] = ()
        if member.security_id:
            ids = build_financial_discovery_identities(session, member.security_id)
            if ids:
                if ids.current_nse_symbol:
                    nse = ids.current_nse_symbol
                nse_symbols = ids.historical_nse_symbols
                hist_bse = ids.historical_bse_codes
        try:
            n, errs = refresh_annual_history_for_bse(
                session,
                bse_code=bse,
                nse_symbol=nse,
                security_id=member.security_id,
                nse_symbols=nse_symbols,
                bse_codes=hist_bse,
                years_back=years_back,
            )
            result.annual_rows_inserted += n
            result.securities_processed += 1
            result.nse_codes += 1
            assert result.errors is not None
            result.errors.extend(errs)
            session.commit()
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            assert result.errors is not None
            result.errors.append(f"{member.display_name}/{bse}: {exc}")
        time.sleep(0.25)
    return result
