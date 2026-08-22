"""Load snapshot context for metric diagnostics."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pms_platform.fundamentals.catalog import COMPUTATION_VERSION
from pms_platform.models.annual_fundamentals_snapshot import AnnualFundamentalsSnapshot
from pms_platform.market_data.price_returns import _load_daily_prices
from pms_platform.models.fundamental_snapshot import FundamentalSnapshot
from pms_platform.models.promoter_snapshot import PromoterSnapshot
from pms_platform.models.valuation_snapshot import ValuationSnapshot
from pms_platform.models.watchlist import WatchlistMember
from pms_platform.watchlists.metric_diagnostics import MemberSnapshotContext, bse_code


def count_prices(session: Session, member: WatchlistMember, bse: str | None) -> int:
    from datetime import date

    if bse:
        rows = _load_daily_prices(session, "BSE_CODE", bse, as_of=date.today())
        if rows:
            return len(rows)
    if member.security_id:
        from pms_platform.models.daily_price import DailyPrice

        return session.scalar(
            select(func.count())
            .select_from(DailyPrice)
            .where(DailyPrice.security_id == member.security_id)
        ) or 0
    return 0


def count_quarterly(session: Session, bse: str | None) -> int:
    if not bse:
        return 0
    return session.scalar(
        select(func.count())
        .select_from(FundamentalSnapshot)
        .where(
            FundamentalSnapshot.identifier_type == "BSE_CODE",
            FundamentalSnapshot.identifier == bse,
            FundamentalSnapshot.computation_version == COMPUTATION_VERSION,
        )
    ) or 0


def load_member_snapshot_context(session: Session, member: WatchlistMember) -> MemberSnapshotContext:
    bse = bse_code(member)
    fund = val = annual = prom = None
    if bse:
        fund = session.scalar(
            select(FundamentalSnapshot)
            .where(
                FundamentalSnapshot.identifier_type == "BSE_CODE",
                FundamentalSnapshot.identifier == bse,
                FundamentalSnapshot.computation_version == COMPUTATION_VERSION,
            )
            .order_by(FundamentalSnapshot.period_end_date.desc())
            .limit(1)
        )
        val = session.scalar(
            select(ValuationSnapshot)
            .where(
                ValuationSnapshot.identifier_type == "BSE_CODE",
                ValuationSnapshot.identifier == bse,
            )
            .order_by(ValuationSnapshot.as_of_date.desc())
            .limit(1)
        )
        annual = session.scalar(
            select(AnnualFundamentalsSnapshot)
            .where(
                AnnualFundamentalsSnapshot.identifier_type == "BSE_CODE",
                AnnualFundamentalsSnapshot.identifier == bse,
            )
            .order_by(AnnualFundamentalsSnapshot.fiscal_year.desc())
            .limit(1)
        )
        prom = session.scalar(
            select(PromoterSnapshot)
            .where(
                PromoterSnapshot.identifier_type == "BSE_CODE",
                PromoterSnapshot.identifier == bse,
            )
            .order_by(PromoterSnapshot.quarter_end_date.desc())
            .limit(1)
        )
    q_rows = count_quarterly(session, bse)
    return MemberSnapshotContext(
        bse_code=bse,
        price_rows=count_prices(session, member, bse),
        quarterly_rows=q_rows,
        has_fund=q_rows > 0,
        has_val=val is not None,
        has_annual=annual is not None,
        has_prom=prom is not None,
        fund_row=fund,
        val_row=val,
        annual_row=annual,
        prom_row=prom,
    )
