"""Reconcile open episodes against live PMS_ClientPortfolio Model sheet.

- Names still OPEN in the ledger but absent from Model are closed.
- Names on Model with no OPEN episode get a Model-sourced open episode so
  Holdings stays in lockstep with Client Portfolio.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from pms_platform.domain.client_positions import resolve_client_portfolio_book
from pms_platform.market_data.nse_bhav_store import (
    latest_bhav_trade_date,
    lookup_bhav_close,
)
from pms_platform.models import DecisionEvent, InvestmentEpisode, Security
from pms_platform.models.enums import DecisionType, EpisodeStatus

_BAD_NSE = frozenset({"", "NAN", "NONE", "NULL"})
# Don't mass-close / mass-open if Model looks empty/broken (OneDrive placeholder).
_MIN_MODEL_SYMBOLS = 3
_SKIP_MODEL = frozenset({"LIQUIDCASE", "LIQUIDBEES"})


@dataclass(frozen=True)
class ModelCloseResult:
    episode_id: int
    security_id: str
    portfolio_name: str
    symbols: tuple[str, ...]
    quantity_closed: int
    exit_date: date
    exit_price: Decimal | None


@dataclass(frozen=True)
class ModelOpenResult:
    episode_id: int
    security_id: str
    portfolio_name: str
    symbol: str
    quantity: int
    entry_date: date


def _nse_symbols(security: Security) -> list[str]:
    out: list[str] = []
    for raw in (security.current_nse_symbol, security.historical_nse_symbol):
        text = str(raw or "").strip().upper()
        if text and text not in _BAD_NSE and text not in out:
            out.append(text)
    return out


def _latest_import_batch_id(session: Session) -> int | None:
    from pms_platform.models.import_batch import ImportBatch

    return session.scalar(select(func.max(ImportBatch.import_batch_id)))


def _find_security_by_nse(session: Session, symbol: str) -> Security | None:
    return session.scalar(
        select(Security)
        .where(
            or_(
                Security.current_nse_symbol == symbol,
                Security.historical_nse_symbol == symbol,
            )
        )
        .limit(1)
    )


def _ensure_security_for_model_symbol(session: Session, symbol: str) -> Security:
    existing = _find_security_by_nse(session, symbol)
    if existing is not None:
        return existing

    batch_id = _latest_import_batch_id(session)
    try:
        from pms_platform.market_data.bse_scrip_universe import resolve_bse_code
        from pms_platform.watchlists.identity_link import upsert_security_from_exchange

        bse = resolve_bse_code(nse_symbol=symbol)
        if bse and batch_id is not None:
            sec, _ = upsert_security_from_exchange(
                session,
                bse=bse,
                nse=symbol,
                isin=None,
                display_name=symbol,
                import_batch_id=batch_id,
            )
            return sec
    except Exception:  # noqa: BLE001 — fall through to synthetic row
        pass

    # ponytail: Model-only names not in Security Master / BSE map
    sid = f"MDL{symbol}"[:16]
    hit = session.get(Security, sid)
    if hit is not None:
        if not hit.current_nse_symbol:
            hit.current_nse_symbol = symbol
        return hit
    base = symbol
    name = base
    n = 2
    while session.scalar(select(Security.security_id).where(Security.portfolio_name == name)):
        name = f"{base}-{n}"
        n += 1
    sec = Security(
        security_id=sid,
        portfolio_name=name,
        canonical_name=symbol,
        current_nse_symbol=symbol,
        status="ACTIVE",
        verification_status="CLIENT_MODEL",
        import_batch_id=batch_id,
    )
    session.add(sec)
    session.flush()
    return sec


def ensure_open_episodes_for_client_model(
    session: Session,
    *,
    as_of: date | None = None,
) -> list[ModelOpenResult]:
    """Open a Holdings episode for each Model symbol that has no OPEN episode."""
    book = resolve_client_portfolio_book(session)
    if book is None:
        return []
    model_rows = [
        pos
        for pos in book.model
        if pos.symbol
        and pos.symbol.upper() not in _SKIP_MODEL
        and pos.qty is not None
        and pos.qty > 0
    ]
    if len(model_rows) < _MIN_MODEL_SYMBOLS:
        return []

    entry_as_of = as_of or latest_bhav_trade_date(session) or date.today()
    securities = {row.security_id: row for row in session.scalars(select(Security)).all()}
    opens = session.scalars(
        select(InvestmentEpisode).where(InvestmentEpisode.status == EpisodeStatus.OPEN.value)
    ).all()
    covered: set[str] = set()
    for episode in opens:
        sec = securities.get(episode.security_id)
        if sec is None:
            continue
        covered.update(_nse_symbols(sec))

    opened: list[ModelOpenResult] = []
    for pos in model_rows:
        symbol = str(pos.symbol).strip().upper()
        if symbol in covered:
            continue
        qty = int(Decimal(pos.qty))
        if qty <= 0:
            continue
        security = _ensure_security_for_model_symbol(session, symbol)
        securities[security.security_id] = security
        already = session.scalar(
            select(InvestmentEpisode).where(
                InvestmentEpisode.security_id == security.security_id,
                InvestmentEpisode.status == EpisodeStatus.OPEN.value,
            )
        )
        if already is not None:
            covered.update(_nse_symbols(security))
            continue

        next_num = (
            session.scalar(
                select(func.coalesce(func.max(InvestmentEpisode.episode_number), 0)).where(
                    InvestmentEpisode.security_id == security.security_id
                )
            )
            or 0
        ) + 1
        entry_price = None
        hit = lookup_bhav_close(session, symbol, entry_as_of)
        if hit is not None:
            entry_price = hit[0]
        elif pos.excel_price is not None:
            entry_price = Decimal(pos.excel_price)

        episode = InvestmentEpisode(
            security_id=security.security_id,
            episode_number=next_num,
            entry_date=entry_as_of,
            exit_date=None,
            status=EpisodeStatus.OPEN.value,
            initial_quantity=qty,
            total_buy_quantity=qty,
            total_sell_quantity=0,
            corporate_action_quantity=0,
            max_quantity=qty,
            final_quantity=qty,
            number_of_buys=1,
            number_of_sells=0,
        )
        session.add(episode)
        session.flush()
        session.add(
            DecisionEvent(
                episode_id=episode.episode_id,
                security_id=security.security_id,
                event_date=entry_as_of,
                decision_type=DecisionType.INITIATE.value,
                quantity_change=qty,
                position_before=0,
                position_after=qty,
                price=entry_price,
                source_transaction_id=None,
            )
        )
        covered.update(_nse_symbols(security))
        covered.add(symbol)
        opened.append(
            ModelOpenResult(
                episode_id=episode.episode_id,
                security_id=security.security_id,
                portfolio_name=security.portfolio_name,
                symbol=symbol,
                quantity=qty,
                entry_date=entry_as_of,
            )
        )

    if opened:
        session.flush()
    return opened


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
    model_symbols -= _SKIP_MODEL
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
