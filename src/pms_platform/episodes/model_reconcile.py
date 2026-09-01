"""Reconcile open episodes against live PMS_ClientPortfolio Model sheet.

Names still OPEN in the transaction ledger but absent from Model are closed
so Holdings / episodes / dashboard treat them as exited. Re-apply after every
``build_episodes`` — a later master import will reopen them only if the sell
is still missing from transactions (then this closes them again).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.domain.client_positions import resolve_client_portfolio_book
from pms_platform.market_data.nse_bhav_store import (
    latest_bhav_trade_date,
    lookup_bhav_close,
)
from pms_platform.models import DecisionEvent, InvestmentEpisode, Security
from pms_platform.models.enums import DecisionType, EpisodeStatus

_BAD_NSE = frozenset({"", "NAN", "NONE", "NULL"})
# Don't mass-close if Model looks empty/broken (OneDrive placeholder, etc.).
_MIN_MODEL_SYMBOLS = 3


@dataclass(frozen=True)
class ModelCloseResult:
    episode_id: int
    security_id: str
    portfolio_name: str
    symbols: tuple[str, ...]
    quantity_closed: int
    exit_date: date
    exit_price: Decimal | None


def _nse_symbols(security: Security) -> list[str]:
    out: list[str] = []
    for raw in (security.current_nse_symbol, security.historical_nse_symbol):
        text = str(raw or "").strip().upper()
        if text and text not in _BAD_NSE and text not in out:
            out.append(text)
    return out


def reconcile_open_episodes_to_client_model(
    session: Session,
    *,
    exit_as_of: date | None = None,
) -> list[ModelCloseResult]:
    """Close OPEN episodes whose NSE tickers are not on the Model sheet.

    Returns closed rows. No-op if the workbook is missing or too thin.
    """
    book = resolve_client_portfolio_book(session)
    if book is None:
        return []
    model_symbols = {pos.symbol for pos in book.model}
    # Cash sleeve is not an equity episode match key.
    model_symbols.discard("LIQUIDCASE")
    if len(model_symbols) < _MIN_MODEL_SYMBOLS:
        return []

    as_of = exit_as_of or latest_bhav_trade_date(session) or date.today()
    securities = {
        row.security_id: row for row in session.scalars(select(Security)).all()
    }
    opens = session.scalars(
        select(InvestmentEpisode).where(
            InvestmentEpisode.status == EpisodeStatus.OPEN.value
        )
    ).all()

    closed: list[ModelCloseResult] = []
    for episode in opens:
        security = securities.get(episode.security_id)
        if security is None:
            continue
        symbols = _nse_symbols(security)
        if not symbols:
            continue
        if any(sym in model_symbols for sym in symbols):
            continue

        qty = int(episode.final_quantity or 0)
        if qty <= 0:
            # Still mark closed for consistency.
            qty = 0

        exit_price: Decimal | None = None
        for sym in symbols:
            hit = lookup_bhav_close(session, sym, as_of)
            if hit is not None:
                exit_price = hit[0]
                break

        episode.status = EpisodeStatus.CLOSED.value
        episode.exit_date = as_of
        episode.final_quantity = 0
        if qty > 0:
            episode.total_sell_quantity = int(episode.total_sell_quantity or 0) + qty
            episode.number_of_sells = int(episode.number_of_sells or 0) + 1
            session.add(
                DecisionEvent(
                    episode_id=episode.episode_id,
                    security_id=episode.security_id,
                    event_date=as_of,
                    decision_type=DecisionType.EXIT.value,
                    quantity_change=-qty,
                    position_before=qty,
                    position_after=0,
                    price=exit_price,
                    source_transaction_id=None,
                )
            )

        closed.append(
            ModelCloseResult(
                episode_id=episode.episode_id,
                security_id=episode.security_id,
                portfolio_name=security.portfolio_name,
                symbols=tuple(symbols),
                quantity_closed=qty,
                exit_date=as_of,
                exit_price=exit_price,
            )
        )

    if closed:
        session.flush()
    return closed
