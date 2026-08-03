"""Equal-weight industry peer returns for open-holding compare."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.analytics.successor_chain import resolve_price_security_id
from pms_platform.market_data.lookup import lookup_daily_price
from pms_platform.market_data.yahoo_finance import YahooFinanceClient
from pms_platform.models import Security

_HUNDRED = Decimal("100")
_ONE = Decimal("1")
_ZERO = Decimal("0")


@dataclass(frozen=True)
class IndustryPeerReturn:
    security_id: str
    portfolio_name: str
    total_return_pct: Decimal | None
    data_status: str


@dataclass(frozen=True)
class IndustryCompareResult:
    security_id: str
    industry: str | None
    peer_count: int
    used_count: int
    total_return_pct: Decimal | None
    peers: tuple[IndustryPeerReturn, ...]
    notes: tuple[str, ...]


def _period_return(
    session: Session,
    security: Security,
    start: date,
    end: date,
    *,
    yahoo: YahooFinanceClient | None,
) -> tuple[Decimal | None, str]:
    start_id = resolve_price_security_id(session, security.security_id, start)
    end_id = resolve_price_security_id(session, security.security_id, end)
    start_obs = lookup_daily_price(session, start_id, start)
    end_obs = lookup_daily_price(session, end_id, end)
    if start_obs is not None and end_obs is not None and start_obs.adjusted_close > 0:
        total = ((end_obs.adjusted_close / start_obs.adjusted_close) - _ONE) * _HUNDRED
        return total, "OK"

    if yahoo is None:
        return None, "MISSING_PRICE"

    symbol = (security.current_nse_symbol or security.historical_nse_symbol or "").strip()
    if not symbol:
        return None, "MISSING_SYMBOL"
    for suffix in (".BO", ".NS"):
        ticker = f"{symbol.upper()}{suffix}"
        try:
            period = yahoo.period_return(ticker, start, end)
        except Exception:  # noqa: BLE001
            continue
        if period is not None:
            return period, "YAHOO"
    return None, "MISSING_PRICE"


def compute_industry_equal_weight(
    session: Session,
    *,
    security_id: str,
    start_date: date,
    end_date: date,
    fetch_yahoo: bool = True,
    client: YahooFinanceClient | None = None,
) -> IndustryCompareResult:
    """Equal-weight return of other securities sharing the same industry."""
    target = session.get(Security, security_id)
    notes: list[str] = []
    if target is None:
        return IndustryCompareResult(
            security_id=security_id,
            industry=None,
            peer_count=0,
            used_count=0,
            total_return_pct=None,
            peers=(),
            notes=("Security not found",),
        )
    industry = (target.industry or "").strip() or None
    if industry is None:
        return IndustryCompareResult(
            security_id=security_id,
            industry=None,
            peer_count=0,
            used_count=0,
            total_return_pct=None,
            peers=(),
            notes=("No industry on security master",),
        )

    peers = list(
        session.scalars(
            select(Security).where(
                Security.industry == industry,
                Security.security_id != security_id,
            )
        ).all()
    )
    yahoo = client if fetch_yahoo else None
    if fetch_yahoo and yahoo is None:
        yahoo = YahooFinanceClient()

    peer_rows: list[IndustryPeerReturn] = []
    used: list[Decimal] = []
    for peer in peers:
        ret, status = _period_return(session, peer, start_date, end_date, yahoo=yahoo)
        peer_rows.append(
            IndustryPeerReturn(
                security_id=peer.security_id,
                portfolio_name=peer.portfolio_name,
                total_return_pct=ret,
                data_status=status,
            )
        )
        if ret is not None:
            used.append(ret)

    if not peers:
        notes.append("No other securities in this industry")
    elif not used:
        notes.append("No peer prices available for the window")

    ew = sum(used, start=_ZERO) / Decimal(len(used)) if used else None
    return IndustryCompareResult(
        security_id=security_id,
        industry=industry,
        peer_count=len(peers),
        used_count=len(used),
        total_return_pct=ew,
        peers=tuple(peer_rows),
        notes=tuple(notes),
    )
