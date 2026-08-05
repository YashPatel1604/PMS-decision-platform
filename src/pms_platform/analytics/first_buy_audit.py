"""Consolidated first-buy price-unit audit for every closed episode."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.analytics.price_units import normalize_transaction_price
from pms_platform.market_data.lookup import lookup_daily_price
from pms_platform.models import DecisionEvent, InvestmentEpisode, Security
from pms_platform.models.enums import EpisodeStatus


@dataclass(frozen=True)
class FirstBuyAuditRow:
    episode_id: int
    security_id: str
    portfolio_name: str
    entry_date: date
    initial_purchase_price: Decimal | None
    entry_market_price: Decimal | None
    inferred_unit_factor: Decimal | None
    normalized_first_buy_price: Decimal | None
    entry_deviation_pct: Decimal | None
    status: str
    note: str


def build_first_buy_price_audit(session: Session) -> list[FirstBuyAuditRow]:
    """Audit first-buy normalization coverage for every closed episode."""
    episodes = session.scalars(
        select(InvestmentEpisode)
        .where(
            InvestmentEpisode.status == EpisodeStatus.CLOSED.value,
            InvestmentEpisode.exit_date.is_not(None),
        )
        .order_by(InvestmentEpisode.episode_id)
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

    audit_rows: list[FirstBuyAuditRow] = []
    for episode in episodes:
        name = (
            securities[episode.security_id].portfolio_name
            if episode.security_id in securities
            else episode.security_id
        )
        initiate = next(
            (
                event
                for event in events_by_episode.get(episode.episode_id, [])
                if event.decision_type == "INITIATE"
                and event.price is not None
                and event.price > 0
                and event.quantity_change > 0
            ),
            None,
        )
        if initiate is None:
            audit_rows.append(
                FirstBuyAuditRow(
                    episode_id=episode.episode_id,
                    security_id=episode.security_id,
                    portfolio_name=name,
                    entry_date=episode.entry_date,
                    initial_purchase_price=None,
                    entry_market_price=None,
                    inferred_unit_factor=None,
                    normalized_first_buy_price=None,
                    entry_deviation_pct=None,
                    status="MISSING_INITIATE",
                    note="No priced INITIATE event; loss triggers are disabled.",
                )
            )
            continue

        market = lookup_daily_price(
            session,
            episode.security_id,
            initiate.event_date,
        )
        if market is None:
            audit_rows.append(
                FirstBuyAuditRow(
                    episode_id=episode.episode_id,
                    security_id=episode.security_id,
                    portfolio_name=name,
                    entry_date=episode.entry_date,
                    initial_purchase_price=initiate.price,
                    entry_market_price=None,
                    inferred_unit_factor=None,
                    normalized_first_buy_price=None,
                    entry_deviation_pct=None,
                    status="MISSING_ENTRY_PRICE",
                    note="No entry-date market price; loss triggers are disabled.",
                )
            )
            continue

        normalization = normalize_transaction_price(
            initiate.price,
            market.adjusted_close,
            security_id=episode.security_id,
            as_of=initiate.event_date,
        )
        if normalization is None:
            audit_rows.append(
                FirstBuyAuditRow(
                    episode_id=episode.episode_id,
                    security_id=episode.security_id,
                    portfolio_name=name,
                    entry_date=episode.entry_date,
                    initial_purchase_price=initiate.price,
                    entry_market_price=market.adjusted_close,
                    inferred_unit_factor=None,
                    normalized_first_buy_price=None,
                    entry_deviation_pct=None,
                    status="INVALID_PRICE",
                    note="Non-positive transaction or market price; loss triggers are disabled.",
                )
            )
            continue

        audit_rows.append(
            FirstBuyAuditRow(
                episode_id=episode.episode_id,
                security_id=episode.security_id,
                portfolio_name=name,
                entry_date=episode.entry_date,
                initial_purchase_price=initiate.price,
                entry_market_price=market.adjusted_close,
                inferred_unit_factor=normalization.inferred_factor,
                normalized_first_buy_price=(
                    normalization.normalized_transaction_price
                ),
                entry_deviation_pct=normalization.entry_deviation_pct,
                status=normalization.status,
                note=(
                    f"Validated via {normalization.factor_source}."
                    if normalization.status == "OK"
                    else "Unit factor requires review; loss triggers are disabled."
                ),
            )
        )
    return audit_rows
