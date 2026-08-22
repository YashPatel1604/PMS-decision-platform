"""Locally derived valuation metrics (PE, PB, market cap, BVPS)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.fundamentals.providers.valuation import upsert_valuation_snapshot
from pms_platform.market_data.price_returns import _load_daily_prices
from pms_platform.models.annual_fundamentals_snapshot import AnnualFundamentalsSnapshot
from pms_platform.models.company_fundamentals_quarterly import CompanyFundamentalsQuarterly
from pms_platform.models.dividend import Dividend
from pms_platform.models.fundamental_snapshot import FundamentalSnapshot
from pms_platform.models.valuation_snapshot import ValuationSnapshot

_HUNDRED = Decimal("100")
_CRORE = Decimal("10000000")


@dataclass
class DerivedValuationResult:
    updated: int
    skipped: int


def _ttm_pat(session: Session, bse_code: str) -> Decimal | None:
    quarters = session.scalars(
        select(CompanyFundamentalsQuarterly)
        .where(
            CompanyFundamentalsQuarterly.identifier_type == "BSE_CODE",
            CompanyFundamentalsQuarterly.identifier == bse_code,
        )
        .order_by(CompanyFundamentalsQuarterly.period_end_date.desc())
        .limit(4)
    ).all()
    if len(quarters) < 4 or any(q.pat is None for q in quarters):
        return None
    return sum((q.pat for q in quarters), Decimal("0"))


def _latest_price(session: Session, bse_code: str, as_of: date) -> Decimal | None:
    prices = _load_daily_prices(session, "BSE_CODE", bse_code, as_of=as_of)
    if prices:
        return prices[-1].adjusted_close
    val = session.scalar(
        select(ValuationSnapshot)
        .where(
            ValuationSnapshot.identifier_type == "BSE_CODE",
            ValuationSnapshot.identifier == bse_code,
        )
        .order_by(ValuationSnapshot.as_of_date.desc())
    )
    return val.last_price if val else None


def _shares_outstanding(
    *,
    price: Decimal,
    market_cap_cr: Decimal | None,
    total_equity_cr: Decimal | None,
    ttm_pat: Decimal | None,
    eps: Decimal | None,
) -> Decimal | None:
    if market_cap_cr and price > 0:
        return (market_cap_cr * _CRORE / price).quantize(Decimal("1"))
    if eps and eps > 0 and ttm_pat and ttm_pat > 0:
        return (ttm_pat * _CRORE / eps).quantize(Decimal("1"))
    return None


def _ttm_dividend_yield(
    session: Session,
    *,
    security_id: str | None,
    price: Decimal,
) -> Decimal | None:
    if not security_id or price <= 0:
        return None
    cutoff = date.today() - timedelta(days=365)
    rows = session.scalars(
        select(Dividend.dividend_per_share).where(
            Dividend.security_id == security_id,
            Dividend.ex_date >= cutoff,
        )
    ).all()
    if not rows:
        return None
    ttm = sum(rows, Decimal("0"))
    if ttm <= 0:
        return None
    return (ttm / price * _HUNDRED).quantize(Decimal("0.0001"))


def derive_valuation_for_code(
    session: Session,
    bse_code: str,
    *,
    as_of: date | None = None,
    force: bool = False,
) -> bool:
    """Fill missing PE/PB/mcap/BVPS from local price + annual + TTM PAT. Returns True if updated."""
    ref = as_of or date.today()
    existing = session.scalar(
        select(ValuationSnapshot)
        .where(
            ValuationSnapshot.identifier_type == "BSE_CODE",
            ValuationSnapshot.identifier == bse_code,
            ValuationSnapshot.as_of_date == ref,
        )
    )
    if existing is None:
        existing = session.scalar(
            select(ValuationSnapshot)
            .where(
                ValuationSnapshot.identifier_type == "BSE_CODE",
                ValuationSnapshot.identifier == bse_code,
            )
            .order_by(ValuationSnapshot.as_of_date.desc())
        )

    price = _latest_price(session, bse_code, ref)
    if price is None or price <= 0:
        return False

    annual = session.scalar(
        select(AnnualFundamentalsSnapshot)
        .where(
            AnnualFundamentalsSnapshot.identifier_type == "BSE_CODE",
            AnnualFundamentalsSnapshot.identifier == bse_code,
        )
        .order_by(AnnualFundamentalsSnapshot.fiscal_year.desc())
    )
    ttm_pat = _ttm_pat(session, bse_code)
    mcap_cr = existing.market_cap_cr if existing else None
    eps = existing.eps if existing else None

    shares = _shares_outstanding(
        price=price,
        market_cap_cr=mcap_cr,
        total_equity_cr=annual.total_equity if annual else None,
        ttm_pat=ttm_pat,
        eps=eps,
    )
    if shares is None or shares <= 0:
        return False

    market_cap_cr = (price * shares / _CRORE).quantize(Decimal("0.01"))
    book_value_per_share: Decimal | None = None
    price_to_book: Decimal | None = None
    if annual and annual.total_equity is not None and annual.total_equity > 0:
        book_value_per_share = (annual.total_equity * _CRORE / shares).quantize(Decimal("0.0001"))
        if book_value_per_share > 0:
            price_to_book = (price / book_value_per_share).quantize(Decimal("0.0001"))

    pe_ratio: Decimal | None = None
    earnings_yield: Decimal | None = None
    if ttm_pat is not None and ttm_pat > 0:
        pe_ratio = (market_cap_cr * _CRORE / (ttm_pat * _CRORE)).quantize(Decimal("0.0001"))
        if pe_ratio and pe_ratio > 0:
            earnings_yield = (_HUNDRED / pe_ratio).quantize(Decimal("0.0001"))
        derived_eps = ((ttm_pat * _CRORE) / shares).quantize(Decimal("0.0001"))
    else:
        derived_eps = eps

    price_to_sales: Decimal | None = None
    snap = session.scalar(
        select(FundamentalSnapshot)
        .where(
            FundamentalSnapshot.identifier_type == "BSE_CODE",
            FundamentalSnapshot.identifier == bse_code,
        )
        .order_by(FundamentalSnapshot.period_end_date.desc())
    )
    if snap and snap.sales:
        q = session.scalars(
            select(CompanyFundamentalsQuarterly)
            .where(
                CompanyFundamentalsQuarterly.identifier_type == "BSE_CODE",
                CompanyFundamentalsQuarterly.identifier == bse_code,
            )
            .order_by(CompanyFundamentalsQuarterly.period_end_date.desc())
            .limit(4)
        ).all()
        if len(q) == 4 and all(x.sales for x in q):
            ttm_sales = sum(x.sales for x in q)
            if ttm_sales > 0:
                price_to_sales = (market_cap_cr / ttm_sales).quantize(Decimal("0.0001"))

    peg_ratio: Decimal | None = None
    if pe_ratio and snap and snap.pat_3y_cagr and snap.pat_3y_cagr > 0:
        peg_ratio = (pe_ratio / snap.pat_3y_cagr).quantize(Decimal("0.0001"))

    sec_id = existing.security_id if existing else None
    if not sec_id:
        from pms_platform.models import Security

        sec_id = session.scalar(
            select(Security.security_id).where(Security.bse_code == bse_code)
        )
    div_yield = _ttm_dividend_yield(session, security_id=sec_id, price=price)

    def _fill(field: str, new_val: Decimal | None) -> Decimal | None:
        if new_val is None:
            return getattr(existing, field, None) if existing else None
        if force or existing is None or getattr(existing, field, None) is None:
            return new_val
        return getattr(existing, field, None)

    upsert_valuation_snapshot(
        session,
        identifier_type="BSE_CODE",
        identifier=bse_code,
        security_id=existing.security_id if existing else None,
        as_of_date=ref,
        last_price=price,
        market_cap_cr=_fill("market_cap_cr", market_cap_cr),
        pe_ratio=_fill("pe_ratio", pe_ratio),
        book_value_per_share=_fill("book_value_per_share", book_value_per_share),
        price_to_book=_fill("price_to_book", price_to_book),
        eps=_fill("eps", derived_eps if ttm_pat and ttm_pat > 0 else None),
        earnings_yield=_fill("earnings_yield", earnings_yield),
        price_to_sales=_fill("price_to_sales", price_to_sales),
        peg_ratio=_fill("peg_ratio", peg_ratio),
        industry_pe=existing.industry_pe if existing else None,
        dividend_yield=_fill("dividend_yield", div_yield) if div_yield is not None else (existing.dividend_yield if existing else None),
        return_1d_pct=existing.return_1d_pct if existing else None,
        return_1m_pct=existing.return_1m_pct if existing else None,
        return_3m_pct=existing.return_3m_pct if existing else None,
        return_6m_pct=existing.return_6m_pct if existing else None,
        return_1y_pct=existing.return_1y_pct if existing else None,
        return_3y_pct=existing.return_3y_pct if existing else None,
        all_time_high=existing.all_time_high if existing else None,
        week_52_high=existing.week_52_high if existing else None,
        week_52_low=existing.week_52_low if existing else None,
        provider="derived_v2",
    )
    return True


def enrich_derived_valuations(
    session: Session,
    bse_codes: list[str],
    *,
    force: bool = False,
) -> DerivedValuationResult:
    updated = skipped = 0
    for code in bse_codes:
        if derive_valuation_for_code(session, code, force=force):
            updated += 1
        else:
            skipped += 1
    session.flush()
    return DerivedValuationResult(updated=updated, skipped=skipped)
