"""Portfolio period-return tests."""

from datetime import date
from decimal import Decimal

from helpers import add_transaction
from pms_platform.analytics.portfolio_value import (
    compute_portfolio_period_return,
    equity_portfolio_market_value,
)
from pms_platform.models import DailyPrice
from pms_platform.models.enums import EventType
from pms_platform.portfolio.position_engine import cumulative_split_bonus_factor_after


def _add_price(session, import_batch, security_id, trade_date, close):
    session.add(
        DailyPrice(
            security_id=security_id,
            identifier_type="SECURITY_ID",
            identifier=security_id,
            trade_date=trade_date,
            close=Decimal(close),
            adjusted_close=Decimal(close),
            adjustment_basis="SPLIT_ONLY",
            volume=None,
            currency="INR",
            source="fixture",
            source_file="fixture.csv",
            source_row=1,
            source_key=f"fixture|{security_id}|{trade_date}",
            import_batch_id=import_batch.import_batch_id,
        )
    )


def test_portfolio_period_return_uses_same_window(session, import_batch, sample_security) -> None:
    other = sample_security
    add_transaction(
        session,
        import_batch,
        other.security_id,
        date(2019, 1, 2),
        EventType.BUY,
        10,
        1,
        Decimal("100"),
    )
    _add_price(session, import_batch, other.security_id, date(2019, 1, 2), "100")
    _add_price(session, import_batch, other.security_id, date(2019, 6, 30), "120")
    session.flush()

    result = compute_portfolio_period_return(
        session,
        start_date=date(2019, 1, 2),
        end_date=date(2019, 6, 30),
    )

    assert result is not None
    assert result.total_return_pct == Decimal("20")


def test_equity_mv_scales_qty_for_later_split(
    session, import_batch, sample_security
) -> None:
    """Adjusted closes already reflect a future split; scale pre-split qty."""
    sid = sample_security.security_id
    add_transaction(
        session, import_batch, sid, date(2025, 1, 2), EventType.BUY, 100, 1, Decimal("1000")
    )
    # 10-for-1 split later: +900 shares when holding 100
    add_transaction(
        session, import_batch, sid, date(2025, 6, 5), EventType.SPLIT, 900, 2
    )
    # Vendor-adjusted close on pre-split date (≈ raw/10)
    _add_price(session, import_batch, sid, date(2025, 3, 31), "100")
    session.flush()

    assert cumulative_split_bonus_factor_after(session, sid, date(2025, 3, 31)) == Decimal(10)
    mv = equity_portfolio_market_value(session, date(2025, 3, 31))
    assert mv == Decimal("100000")  # 100 * 10 * 100

    # After the split, factor is 1 and ledger qty is already 1000
    _add_price(session, import_batch, sid, date(2025, 6, 30), "105")
    session.flush()
    assert cumulative_split_bonus_factor_after(session, sid, date(2025, 6, 30)) == Decimal(1)
    assert equity_portfolio_market_value(session, date(2025, 6, 30)) == Decimal("105000")
