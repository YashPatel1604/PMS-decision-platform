"""Open-holding analytics from entry date through a chosen as-of date."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.analytics.benchmark import compute_benchmark_period_return
from pms_platform.analytics.ownership_metrics import (
    _cost_state_on_date,
    _episode_first_buy_states,
)
from pms_platform.analytics.portfolio_value import (
    compute_portfolio_period_return,
    equity_portfolio_market_value,
    list_security_trading_dates,
)
from pms_platform.analytics.research_portfolio_value import (
    latest_research_book_date,
    lookup_research_portfolio_value,
)
from pms_platform.analytics.successor_chain import resolve_price_security_id
from pms_platform.market_data.client_portfolio_parse import (
    ClientPortfolioPosition,
    load_client_portfolio_book,
)
from pms_platform.market_data.contracts import REQUIRED_BENCHMARKS
from pms_platform.market_data.lookup import lookup_daily_price
from pms_platform.market_data.nse_bhav_store import (
    latest_bhav_trade_date,
    lookup_bhav_close,
)
from pms_platform.models import DecisionEvent, InvestmentEpisode, Security
from pms_platform.models.enums import EpisodeStatus
from pms_platform.portfolio.position_engine import cumulative_split_bonus_factor_after

_HUNDRED = Decimal("100")
_ONE = Decimal("1")
_ZERO = Decimal("0")
_BAD_NSE = frozenset({"", "NAN", "NONE", "NULL"})


def latest_holdings_as_of(session: Session) -> date | None:
    """Ceiling for Current Holdings: latest History book or committed bhav day."""
    book = latest_research_book_date()
    bhav = latest_bhav_trade_date(session)
    candidates = [day for day in (book, bhav) if day is not None]
    return max(candidates) if candidates else None


def _nse_symbols(security: Security | None) -> list[str]:
    if security is None:
        return []
    out: list[str] = []
    for raw in (security.current_nse_symbol, security.historical_nse_symbol):
        text = str(raw or "").strip().upper()
        if text and text not in _BAD_NSE and text not in out:
            out.append(text)
    return out


def _bhav_close_for_security(
    session: Session,
    security: Security | None,
    as_of_date: date,
) -> tuple[Decimal, str] | None:
    """Raw NSE bhav CMP for a security on ``as_of_date`` (EQ then BE)."""
    for symbol in _nse_symbols(security):
        hit = lookup_bhav_close(session, symbol, as_of_date)
        if hit is not None:
            return hit
    return None


def _model_position_for_security(
    security: Security | None,
    model_by_symbol: dict[str, ClientPortfolioPosition],
) -> ClientPortfolioPosition | None:
    for symbol in _nse_symbols(security):
        if symbol in model_by_symbol:
            return model_by_symbol[symbol]
    return None


def _client_model_bhav_total(
    session: Session,
    as_of_date: date,
    model_by_symbol: dict[str, ClientPortfolioPosition],
) -> Decimal | None:
    """Sum Model qty × bhav (Excel price fallback) — matches Client Portfolio dashboard."""
    if not model_by_symbol:
        return None
    total = _ZERO
    priced = 0
    for pos in model_by_symbol.values():
        hit = lookup_bhav_close(session, pos.symbol, as_of_date)
        price = hit[0] if hit is not None else pos.excel_price
        if price is None:
            continue
        total += pos.qty * price
        priced += 1
    return total if priced else None


@dataclass(frozen=True)
class HoldingBenchmarkComparison:
    """Stock versus one registered benchmark over the holding window."""

    code: str
    total_return_pct: Decimal | None
    excess_vs_stock_pp: Decimal | None
    start_level: Decimal | None
    end_level: Decimal | None
    data_status: str


@dataclass(frozen=True)
class OpenHoldingRow:
    """One open episode valued through an as-of date."""

    episode_id: int
    security_id: str
    portfolio_name: str
    entry_date: date
    as_of_date: date
    period_start_date: date
    quantity: int
    average_buy_price: Decimal | None
    first_buy_price: Decimal | None
    from_price: Decimal | None
    from_price_date: date | None
    as_of_price: Decimal | None
    as_of_price_date: date | None
    market_value: Decimal | None
    cost_basis_value: Decimal | None
    unrealized_pnl: Decimal | None
    unrealized_pnl_pct: Decimal | None
    stock_return_pct: Decimal | None
    portfolio_return_pct: Decimal | None
    excess_vs_portfolio_pp: Decimal | None
    bse_return_pct: Decimal | None
    excess_vs_bse_pp: Decimal | None
    holding_days: int
    period_days: int
    position_weight_pct: Decimal | None
    underwater: bool
    days_below_first_buy: int | None
    sector: str | None
    industry: str | None
    benchmarks: tuple[HoldingBenchmarkComparison, ...]
    data_quality_status: str
    notes: tuple[str, ...]


@dataclass(frozen=True)
class OpenHoldingsResult:
    """Portfolio-level open holdings snapshot."""

    as_of_date: date
    from_date: date | None
    open_count: int
    equity_market_value: Decimal | None
    equity_market_value_from: Decimal | None
    portfolio_return_pct: Decimal | None
    mean_excess_vs_primary_pp: Decimal | None
    mean_excess_vs_portfolio_pp: Decimal | None
    primary_benchmark_code: str
    benchmark_codes: tuple[str, ...]
    holdings: tuple[OpenHoldingRow, ...]
    live_refresh: dict[str, object] | None = None
    reconstructed_equity_market_value: Decimal | None = None
    reconstructed_equity_market_value_from: Decimal | None = None
    portfolio_value_source: str | None = None
    portfolio_value_from_source: str | None = None
    portfolio_value_observation_date: date | None = None
    portfolio_value_from_observation_date: date | None = None
    portfolio_value_check_delta: Decimal | None = None
    portfolio_value_from_check_delta: Decimal | None = None


def default_benchmark_codes() -> tuple[str, ...]:
    """Return the configured default comparison set."""
    return REQUIRED_BENCHMARKS


def _parse_benchmark_codes(raw: str | None) -> tuple[str, ...]:
    if raw is None or not raw.strip():
        return default_benchmark_codes()
    codes = tuple(code.strip() for code in raw.split(",") if code.strip())
    return codes or default_benchmark_codes()


def _average_buy_price(events: list[DecisionEvent]) -> Decimal | None:
    buy_value = _ZERO
    buy_qty = _ZERO
    for event in events:
        if event.price is None or event.price <= 0:
            continue
        if event.decision_type not in {"INITIATE", "ADD"}:
            continue
        qty = abs(Decimal(event.quantity_change))
        if qty <= 0:
            continue
        buy_value += event.price * qty
        buy_qty += qty
    return buy_value / buy_qty if buy_qty > 0 else None


def _quantity_on_date(events: list[DecisionEvent], as_of_date: date) -> int:
    quantity = 0
    for event in sorted(events, key=lambda row: (row.event_date, row.decision_event_id)):
        if event.event_date > as_of_date:
            break
        quantity = event.position_after
    return quantity


def _stock_return_pct(
    session: Session,
    security_id: str,
    start_date: date,
    as_of_date: date,
    *,
    security: Security | None = None,
) -> tuple[Decimal | None, date | None, date | None, Decimal | None, str | None]:
    """Return stock total return, observation dates, and start price used."""
    start_security_id = resolve_price_security_id(session, security_id, start_date)
    end_security_id = resolve_price_security_id(session, security_id, as_of_date)
    start = lookup_daily_price(
        session, start_security_id, start_date, allow_live=False
    )
    end = lookup_daily_price(
        session, end_security_id, as_of_date, allow_live=False
    )
    end_close: Decimal | None = end.adjusted_close if end is not None else None
    end_date_obs: date | None = end.trade_date if end is not None else None
    if end_close is None:
        # ponytail: raw bhav CMP when daily_prices lag the latest bhav session
        bhav = _bhav_close_for_security(session, security, as_of_date)
        if bhav is not None:
            end_close, _series = bhav
            end_date_obs = as_of_date
    if start is None:
        return None, None, end_date_obs, None, "Missing period-start price"
    if end_close is None:
        return None, start.trade_date, None, start.adjusted_close, "Missing as-of price"
    if start.adjusted_close <= 0:
        return (
            None,
            start.trade_date,
            end_date_obs,
            start.adjusted_close,
            "Non-positive period-start price",
        )
    total = ((end_close / start.adjusted_close) - _ONE) * _HUNDRED
    return total, start.trade_date, end_date_obs, start.adjusted_close, None


def _days_below_first_buy(
    session: Session,
    security_id: str,
    entry_date: date,
    as_of_date: date,
    events: list[DecisionEvent],
) -> tuple[bool, int | None]:
    cost_states = _episode_first_buy_states(session, security_id, events)
    if not cost_states:
        return False, None
    trading_dates = list_security_trading_dates(session, security_id, entry_date, as_of_date)
    days_below = 0
    underwater_now = False
    for trade_date in trading_dates:
        state = _cost_state_on_date(cost_states, trade_date)
        if state is None:
            continue
        price_security_id = resolve_price_security_id(session, security_id, trade_date)
        observation = lookup_daily_price(
            session, price_security_id, trade_date, allow_live=False
        )
        if observation is None:
            continue
        if observation.adjusted_close < state.first_buy_price:
            days_below += 1
            if trade_date == trading_dates[-1] or trade_date == as_of_date:
                underwater_now = True
    if trading_dates:
        latest = trading_dates[-1]
        state = _cost_state_on_date(cost_states, latest)
        if state is not None:
            price_security_id = resolve_price_security_id(session, security_id, latest)
            observation = lookup_daily_price(
                session, price_security_id, latest, allow_live=False
            )
            if observation is not None:
                underwater_now = observation.adjusted_close < state.first_buy_price
    return underwater_now, days_below


def _benchmark_comparisons(
    session: Session,
    *,
    entry_date: date,
    as_of_date: date,
    stock_return_pct: Decimal | None,
    benchmark_codes: tuple[str, ...],
) -> tuple[HoldingBenchmarkComparison, ...]:
    rows: list[HoldingBenchmarkComparison] = []
    for code in benchmark_codes:
        period = compute_benchmark_period_return(
            session,
            benchmark_code=code,
            start_date=entry_date,
            end_date=as_of_date,
        )
        if period is None:
            rows.append(
                HoldingBenchmarkComparison(
                    code=code,
                    total_return_pct=None,
                    excess_vs_stock_pp=None,
                    start_level=None,
                    end_level=None,
                    data_status="INSUFFICIENT",
                )
            )
            continue
        excess = (
            stock_return_pct - period.total_return_pct
            if stock_return_pct is not None
            else None
        )
        rows.append(
            HoldingBenchmarkComparison(
                code=code,
                total_return_pct=period.total_return_pct,
                excess_vs_stock_pp=excess,
                start_level=period.start_level,
                end_level=period.end_level,
                data_status="OK",
            )
        )
    return tuple(rows)


def _portfolio_return_cached(
    session: Session,
    cache: dict[tuple[date, date], Decimal | None],
    start: date,
    end: date,
) -> Decimal | None:
    key = (start, end)
    if key not in cache:
        period = compute_portfolio_period_return(session, start_date=start, end_date=end)
        cache[key] = period.total_return_pct if period is not None else None
    return cache[key]


def _bse_from_benchmarks(
    benchmarks: tuple[HoldingBenchmarkComparison, ...],
    primary: str,
) -> tuple[Decimal | None, Decimal | None]:
    for item in benchmarks:
        if item.code == primary:
            return item.total_return_pct, item.excess_vs_stock_pp
    if benchmarks:
        return benchmarks[0].total_return_pct, benchmarks[0].excess_vs_stock_pp
    return None, None


def _analyze_open_episode(
    session: Session,
    episode: InvestmentEpisode,
    events: list[DecisionEvent],
    security: Security | None,
    as_of_date: date,
    equity_mv: Decimal | None,
    benchmark_codes: tuple[str, ...],
    *,
    from_date: date | None = None,
    portfolio_cache: dict[tuple[date, date], Decimal | None] | None = None,
    model_by_symbol: dict[str, ClientPortfolioPosition] | None = None,
) -> OpenHoldingRow:
    notes: list[str] = []
    portfolio_name = (
        security.portfolio_name
        if security is not None and security.portfolio_name
        else episode.security_id
    )
    sector = security.sector if security is not None else None
    industry = security.industry if security is not None else None
    cache = portfolio_cache if portfolio_cache is not None else {}
    primary = benchmark_codes[0] if benchmark_codes else default_benchmark_codes()[0]

    # Period window: optional from_date, never before entry.
    period_start = episode.entry_date
    if from_date is not None:
        period_start = max(from_date, episode.entry_date)
        if from_date > episode.entry_date:
            notes.append(f"Period starts {period_start.isoformat()} (from-date window)")
        elif from_date < episode.entry_date:
            notes.append("Entered after from-date; period starts at entry")

    def _empty_row(
        *,
        quantity: int = 0,
        holding_days: int = 0,
        period_days: int = 0,
        status: str = "INSUFFICIENT",
    ) -> OpenHoldingRow:
        benchmarks = _benchmark_comparisons(
            session,
            entry_date=period_start,
            as_of_date=as_of_date,
            stock_return_pct=None,
            benchmark_codes=benchmark_codes,
        )
        bse_ret, _ = _bse_from_benchmarks(benchmarks, primary)
        port_ret = (
            _portfolio_return_cached(session, cache, period_start, as_of_date)
            if as_of_date >= period_start
            else None
        )
        return OpenHoldingRow(
            episode_id=episode.episode_id,
            security_id=episode.security_id,
            portfolio_name=portfolio_name,
            entry_date=episode.entry_date,
            as_of_date=as_of_date,
            period_start_date=period_start,
            quantity=quantity,
            average_buy_price=None,
            first_buy_price=None,
            from_price=None,
            from_price_date=None,
            as_of_price=None,
            as_of_price_date=None,
            market_value=None,
            cost_basis_value=None,
            unrealized_pnl=None,
            unrealized_pnl_pct=None,
            stock_return_pct=None,
            portfolio_return_pct=port_ret,
            excess_vs_portfolio_pp=None,
            bse_return_pct=bse_ret,
            excess_vs_bse_pp=None,
            holding_days=holding_days,
            period_days=period_days,
            position_weight_pct=None,
            underwater=False,
            days_below_first_buy=None,
            sector=sector,
            industry=industry,
            benchmarks=benchmarks,
            data_quality_status=status,
            notes=tuple(notes),
        )

    if as_of_date < episode.entry_date:
        notes.append("As-of date is before entry date")
        return _empty_row()

    if as_of_date < period_start:
        notes.append("As-of date is before period start")
        return _empty_row(holding_days=max((as_of_date - episode.entry_date).days, 0))

    quantity = _quantity_on_date(events, as_of_date)
    model_pos = _model_position_for_security(security, model_by_symbol or {})
    if model_pos is not None:
        model_qty = int(model_pos.qty)
        if model_qty != quantity:
            notes.append(f"Qty from Model sheet ({model_qty}); episode ledger was {quantity}")
        quantity = model_qty
    average_buy = _average_buy_price(events)
    cost_states = _episode_first_buy_states(session, episode.security_id, events)
    cost_state = _cost_state_on_date(cost_states, as_of_date)
    first_buy = cost_state.first_buy_price if cost_state is not None else None

    price_security_id = resolve_price_security_id(session, episode.security_id, as_of_date)
    as_of_obs = lookup_daily_price(
        session, price_security_id, as_of_date, allow_live=False
    )
    as_of_adj = as_of_obs.adjusted_close if as_of_obs is not None else None
    as_of_price_date = as_of_obs.trade_date if as_of_obs is not None else None
    # Pair ledger qty with adjusted prices via later split/bonus factors;
    # present price on the as-of share-count basis (matches Model Portfolio CMP).
    as_of_factor = cumulative_split_bonus_factor_after(
        session, episode.security_id, as_of_date
    )
    as_of_price = as_of_adj * as_of_factor if as_of_adj is not None else None
    bhav_mark = _bhav_close_for_security(session, security, as_of_date)
    if bhav_mark is not None:
        # Bhav CMP is already on current share count — prefer it when present.
        as_of_price, _bhav_series = bhav_mark
        as_of_price_date = as_of_date

    market_value = (
        as_of_price * Decimal(quantity) if as_of_price is not None and quantity > 0 else None
    )
    cost_basis_value = (
        average_buy * Decimal(quantity) if average_buy is not None and quantity > 0 else None
    )
    unrealized_pnl = (
        market_value - cost_basis_value
        if market_value is not None and cost_basis_value is not None
        else None
    )
    unrealized_pnl_pct = (
        (unrealized_pnl / cost_basis_value) * _HUNDRED
        if unrealized_pnl is not None and cost_basis_value is not None and cost_basis_value > 0
        else None
    )
    weight = (
        (market_value / equity_mv) * _HUNDRED
        if market_value is not None and equity_mv is not None and equity_mv > 0
        else None
    )

    # Period market path still fills from_price for diagnostics; headline Stock %
    # is 1st buy → current (not avg buy, not period-start close).
    _, from_price_date, _, from_adj, period_note = _stock_return_pct(
        session,
        episode.security_id,
        period_start,
        as_of_date,
        security=security,
    )
    if as_of_price is None:
        notes.append("Missing as-of price")
    if first_buy is None:
        notes.append("Missing first-buy threshold")
    elif first_buy <= 0:
        notes.append("Non-positive first-buy price")

    from_factor = cumulative_split_bonus_factor_after(
        session, episode.security_id, period_start
    )
    from_price = from_adj * from_factor if from_adj is not None else None

    if first_buy is not None and first_buy > 0 and as_of_price is not None:
        stock_return = ((as_of_price / first_buy) - _ONE) * _HUNDRED
    else:
        stock_return = None
        if period_note:
            notes.append(period_note)

    underwater, days_below = _days_below_first_buy(
        session,
        episode.security_id,
        episode.entry_date,
        as_of_date,
        events,
    )
    benchmarks = _benchmark_comparisons(
        session,
        entry_date=period_start,
        as_of_date=as_of_date,
        stock_return_pct=stock_return,
        benchmark_codes=benchmark_codes,
    )
    from pms_platform.analytics.portfolio_calendar_returns import (
        linked_bse_smallcap_return_pct,
    )

    bse_nav = linked_bse_smallcap_return_pct(period_start, as_of_date)
    if bse_nav is not None:
        bse_ret = bse_nav
        excess_bse = (
            stock_return - bse_ret if stock_return is not None else None
        )
    else:
        bse_ret, excess_bse = _bse_from_benchmarks(benchmarks, primary)
    port_ret = _portfolio_return_cached(session, cache, period_start, as_of_date)
    excess_port = (
        stock_return - port_ret if stock_return is not None and port_ret is not None else None
    )

    status = "OK" if stock_return is not None and as_of_price is not None else "INSUFFICIENT"
    return OpenHoldingRow(
        episode_id=episode.episode_id,
        security_id=episode.security_id,
        portfolio_name=portfolio_name,
        entry_date=episode.entry_date,
        as_of_date=as_of_date,
        period_start_date=period_start,
        quantity=quantity,
        average_buy_price=average_buy,
        first_buy_price=first_buy,
        from_price=from_price,
        from_price_date=from_price_date,
        as_of_price=as_of_price,
        as_of_price_date=as_of_price_date,
        market_value=market_value,
        cost_basis_value=cost_basis_value,
        unrealized_pnl=unrealized_pnl,
        unrealized_pnl_pct=unrealized_pnl_pct,
        stock_return_pct=stock_return,
        portfolio_return_pct=port_ret,
        excess_vs_portfolio_pp=excess_port,
        bse_return_pct=bse_ret,
        excess_vs_bse_pp=excess_bse,
        holding_days=max((as_of_date - episode.entry_date).days, 0),
        period_days=max((as_of_date - period_start).days, 0),
        position_weight_pct=weight,
        underwater=underwater,
        days_below_first_buy=days_below,
        sector=sector,
        industry=industry,
        benchmarks=benchmarks,
        data_quality_status=status,
        notes=tuple(notes),
    )


def analyze_open_holdings(
    session: Session,
    *,
    as_of_date: date | None = None,
    from_date: date | None = None,
    benchmarks: str | None = None,
    episode_id: int | None = None,
    refresh_live: bool = False,
) -> OpenHoldingsResult:
    """Compute open-holding metrics through an as-of date.

    As-of defaults to (and is capped at) the later of:
    - latest Research History / Values book date
    - latest committed NSE bhav session (Pivot upload)

    Per-name marks prefer that day's bhav close when present; otherwise EOD
    daily_prices. When ``PMS_ClientPortfolio.xlsx`` Model has the symbol, qty
    follows Model (episode ledger noted if different). Yahoo live quotes are
    never applied.
    """
    del refresh_live  # Holdings never refresh or use Yahoo live marks.
    # Close ledger-open names that dad already dropped from Model (e.g. WelEnt).
    from pms_platform.episodes.model_reconcile import reconcile_open_episodes_to_client_model

    closed_now = reconcile_open_episodes_to_client_model(session)
    if closed_now:
        # Populate EpisodePerformance / post-exit so Dashboard & Episodes see them.
        from pms_platform.analytics.service import run_full_episode_analysis

        run_full_episode_analysis(session)
        session.commit()

    ceiling = latest_holdings_as_of(session)
    if as_of_date is None:
        resolved_as_of = ceiling or date.today()
    elif ceiling is not None and as_of_date > ceiling:
        resolved_as_of = ceiling
    else:
        resolved_as_of = as_of_date
    if from_date is not None and from_date > resolved_as_of:
        msg = f"from_date {from_date} is after as_of_date {resolved_as_of}"
        raise ValueError(msg)
    benchmark_codes = _parse_benchmark_codes(benchmarks)
    primary = benchmark_codes[0] if benchmark_codes else default_benchmark_codes()[0]
    live_refresh: dict[str, object] | None = None

    client_book = load_client_portfolio_book()
    model_by_symbol = (
        {pos.symbol: pos for pos in client_book.model} if client_book is not None else {}
    )

    query = select(InvestmentEpisode).where(
        InvestmentEpisode.status == EpisodeStatus.OPEN.value
    )
    if episode_id is not None:
        query = query.where(InvestmentEpisode.episode_id == episode_id)
    episodes = session.scalars(
        query.order_by(InvestmentEpisode.entry_date, InvestmentEpisode.episode_id)
    ).all()

    securities = {
        row.security_id: row for row in session.scalars(select(Security)).all()
    }
    episode_ids = [row.episode_id for row in episodes]
    events_by_episode: dict[int, list[DecisionEvent]] = {}
    if episode_ids:
        for event in session.scalars(
            select(DecisionEvent)
            .where(DecisionEvent.episode_id.in_(episode_ids))
            .order_by(
                DecisionEvent.episode_id,
                DecisionEvent.event_date,
                DecisionEvent.decision_event_id,
            )
        ).all():
            events_by_episode.setdefault(event.episode_id, []).append(event)

    equity_mv_reconstructed = equity_portfolio_market_value(
        session, resolved_as_of, allow_live=False
    )
    research_as_of = lookup_research_portfolio_value(resolved_as_of)
    model_bhav_total = _client_model_bhav_total(session, resolved_as_of, model_by_symbol)
    # Exact History/Values day wins; if Research is stale vs as-of (bhav ahead),
    # prefer live Model×bhav (same as Client Portfolio), else reconstructed.
    if (
        research_as_of is not None
        and research_as_of.observation_date == resolved_as_of
    ):
        equity_mv = research_as_of.value
        portfolio_value_source = research_as_of.source
        portfolio_value_observation_date = research_as_of.observation_date
        portfolio_value_check_delta = (
            equity_mv - equity_mv_reconstructed
            if equity_mv_reconstructed is not None
            else None
        )
    elif model_bhav_total is not None:
        equity_mv = model_bhav_total
        portfolio_value_source = "CLIENT_MODEL_BHAV"
        portfolio_value_observation_date = resolved_as_of
        portfolio_value_check_delta = (
            equity_mv - equity_mv_reconstructed
            if equity_mv_reconstructed is not None
            else None
        )
    else:
        equity_mv = equity_mv_reconstructed
        bhav_day = latest_bhav_trade_date(session)
        if equity_mv is not None and bhav_day is not None and resolved_as_of == bhav_day:
            portfolio_value_source = "BHAV_REVALUED"
        else:
            portfolio_value_source = "RECONSTRUCTED" if equity_mv is not None else None
        portfolio_value_observation_date = (
            resolved_as_of if equity_mv is not None else None
        )
        portfolio_value_check_delta = _ZERO if equity_mv is not None else None

    portfolio_cache: dict[tuple[date, date], Decimal | None] = {}
    holdings = [
        _analyze_open_episode(
            session,
            episode,
            events_by_episode.get(episode.episode_id, []),
            securities.get(episode.security_id),
            resolved_as_of,
            equity_mv,
            benchmark_codes,
            from_date=from_date,
            portfolio_cache=portfolio_cache,
            model_by_symbol=model_by_symbol,
        )
        for episode in episodes
    ]

    excesses = []
    port_excesses = []
    for row in holdings:
        if row.excess_vs_bse_pp is not None:
            excesses.append(row.excess_vs_bse_pp)
        if row.excess_vs_portfolio_pp is not None:
            port_excesses.append(row.excess_vs_portfolio_pp)
    mean_excess = sum(excesses, start=_ZERO) / Decimal(len(excesses)) if excesses else None
    mean_port_excess = (
        sum(port_excesses, start=_ZERO) / Decimal(len(port_excesses)) if port_excesses else None
    )

    book_portfolio_return: Decimal | None = None
    equity_mv_from: Decimal | None = None
    equity_mv_from_reconstructed: Decimal | None = None
    portfolio_value_from_source: str | None = None
    portfolio_value_from_observation_date: date | None = None
    portfolio_value_from_check_delta: Decimal | None = None
    if from_date is not None:
        equity_mv_from_reconstructed = equity_portfolio_market_value(
            session, from_date, allow_live=False
        )
        research_from = lookup_research_portfolio_value(from_date)
        if research_from is not None:
            equity_mv_from = research_from.value
            portfolio_value_from_source = research_from.source
            portfolio_value_from_observation_date = research_from.observation_date
            portfolio_value_from_check_delta = (
                equity_mv_from - equity_mv_from_reconstructed
                if equity_mv_from_reconstructed is not None
                else None
            )
        else:
            equity_mv_from = equity_mv_from_reconstructed
            portfolio_value_from_source = (
                "RECONSTRUCTED" if equity_mv_from is not None else None
            )
            portfolio_value_from_observation_date = (
                from_date if equity_mv_from is not None else None
            )
            portfolio_value_from_check_delta = _ZERO if equity_mv_from is not None else None

        if (
            equity_mv_from is not None
            and equity_mv is not None
            and equity_mv_from > 0
            and portfolio_value_source != "RECONSTRUCTED"
            and portfolio_value_from_source != "RECONSTRUCTED"
        ):
            # Prefer contribution-neutral calendar TWR over book AUM growth.
            book_portfolio_return = _portfolio_return_cached(
                session, portfolio_cache, from_date, resolved_as_of
            )
            if book_portfolio_return is None:
                book_portfolio_return = ((equity_mv / equity_mv_from) - _ONE) * _HUNDRED
        else:
            book_portfolio_return = _portfolio_return_cached(
                session, portfolio_cache, from_date, resolved_as_of
            )

    return OpenHoldingsResult(
        as_of_date=resolved_as_of,
        from_date=from_date,
        open_count=len(holdings),
        equity_market_value=equity_mv,
        equity_market_value_from=equity_mv_from,
        portfolio_return_pct=book_portfolio_return,
        mean_excess_vs_primary_pp=mean_excess,
        mean_excess_vs_portfolio_pp=mean_port_excess,
        primary_benchmark_code=primary,
        benchmark_codes=benchmark_codes,
        holdings=tuple(holdings),
        live_refresh=live_refresh,
        reconstructed_equity_market_value=equity_mv_reconstructed,
        reconstructed_equity_market_value_from=equity_mv_from_reconstructed,
        portfolio_value_source=portfolio_value_source,
        portfolio_value_from_source=portfolio_value_from_source,
        portfolio_value_observation_date=portfolio_value_observation_date,
        portfolio_value_from_observation_date=portfolio_value_from_observation_date,
        portfolio_value_check_delta=portfolio_value_check_delta,
        portfolio_value_from_check_delta=portfolio_value_from_check_delta,
    )
