"""Investment episode generation."""

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from pms_platform.models import DecisionEvent, InvestmentEpisode, Transaction
from pms_platform.models.enums import DecisionType, EpisodeStatus, EventType


@dataclass
class EpisodeAccumulator:
    """Mutable state while building one episode."""

    security_id: str
    episode_number: int
    entry_date: date
    initial_quantity: int
    total_buy_quantity: int = 0
    total_sell_quantity: int = 0
    corporate_action_quantity: int = 0
    max_quantity: int = 0
    final_quantity: int = 0
    number_of_buys: int = 0
    number_of_sells: int = 0
    status: EpisodeStatus = EpisodeStatus.OPEN
    exit_date: date | None = None
    decision_events: list[DecisionEvent] = field(default_factory=list)


EPISODE_ENTRY_CORPORATE_ACTIONS = frozenset(
    {EventType.DEMERGER, EventType.MERGER, EventType.CONVERSION}
)


def _opens_episode(event_type: EventType, position_before: int, position_after: int) -> bool:
    """Return True when a transaction should start a new investment episode."""
    if position_before != 0 or position_after <= 0:
        return False
    if event_type == EventType.BUY:
        return True
    return event_type in EPISODE_ENTRY_CORPORATE_ACTIONS


def _decision_type_for(
    event_type: EventType, position_before: int, position_after: int
) -> DecisionType:
    """Map a transaction to a decision event type."""
    if event_type in EventType.corporate_actions():
        return DecisionType.CORPORATE_ACTION
    if event_type == EventType.BUY:
        return DecisionType.INITIATE if position_before == 0 else DecisionType.ADD
    if event_type == EventType.SELL:
        return DecisionType.EXIT if position_after == 0 else DecisionType.REDUCE
    msg = f"Unsupported event type for decision mapping: {event_type}"
    raise ValueError(msg)


def build_episodes(session: Session) -> tuple[list[InvestmentEpisode], list[DecisionEvent]]:
    """Rebuild investment episodes and decision events from all equity transactions."""
    from pms_platform.models import (
        EpisodeCashFlowRecord,
        EpisodePerformance,
        PostExitHorizonPerformance,
        PostExitPerformance,
        SellAssessment,
    )

    session.execute(delete(PostExitHorizonPerformance))
    session.execute(delete(PostExitPerformance))
    session.execute(delete(SellAssessment))
    session.execute(delete(EpisodePerformance))
    session.execute(delete(EpisodeCashFlowRecord))
    session.execute(delete(DecisionEvent))
    session.execute(delete(InvestmentEpisode))
    session.flush()

    transactions = list(
        session.scalars(
            select(Transaction).order_by(
                Transaction.security_id,
                Transaction.event_date,
                Transaction.source_row,
            )
        ).all()
    )

    episodes: list[InvestmentEpisode] = []
    all_decision_events: list[DecisionEvent] = []

    current_security: str | None = None
    episode_number = 0
    running_quantity = 0
    accumulator: EpisodeAccumulator | None = None

    def finalize_episode() -> None:
        nonlocal accumulator
        if accumulator is None:
            return
        episode = InvestmentEpisode(
            security_id=accumulator.security_id,
            episode_number=accumulator.episode_number,
            entry_date=accumulator.entry_date,
            exit_date=accumulator.exit_date,
            status=accumulator.status.value,
            initial_quantity=accumulator.initial_quantity,
            total_buy_quantity=accumulator.total_buy_quantity,
            total_sell_quantity=accumulator.total_sell_quantity,
            corporate_action_quantity=accumulator.corporate_action_quantity,
            max_quantity=accumulator.max_quantity,
            final_quantity=accumulator.final_quantity,
            number_of_buys=accumulator.number_of_buys,
            number_of_sells=accumulator.number_of_sells,
        )
        session.add(episode)
        session.flush()
        episode_events = accumulator.decision_events
        for event in episode_events:
            event.episode_id = episode.episode_id
            session.add(event)
        episodes.append(episode)
        all_decision_events.extend(episode_events)
        accumulator = None

    for txn in transactions:
        if current_security != txn.security_id:
            finalize_episode()
            current_security = txn.security_id
            episode_number = 0
            running_quantity = 0

        event_type = EventType.from_workbook(txn.event_type)
        position_before = running_quantity
        position_after = running_quantity + txn.quantity

        if _opens_episode(event_type, position_before, position_after):
            episode_number += 1
            initial_quantity = txn.quantity if event_type == EventType.BUY else position_after
            accumulator = EpisodeAccumulator(
                security_id=txn.security_id,
                episode_number=episode_number,
                entry_date=txn.event_date,
                initial_quantity=initial_quantity,
            )

        if accumulator is None and event_type in EventType.corporate_actions():
            msg = (
                f"Corporate action outside active episode for {txn.security_id} "
                f"on {txn.event_date} ({txn.source_key})"
            )
            raise ValueError(msg)

        if accumulator is None and event_type in {EventType.SELL, EventType.BUY}:
            if not (event_type == EventType.SELL and position_before == 0):
                msg = (
                    f"Transaction outside active episode for {txn.security_id} on {txn.event_date}"
                )
                raise ValueError(msg)

        if accumulator is not None:
            if event_type == EventType.BUY:
                accumulator.total_buy_quantity += txn.quantity
                accumulator.number_of_buys += 1
            elif event_type == EventType.SELL:
                accumulator.total_sell_quantity += abs(txn.quantity)
                accumulator.number_of_sells += 1
            elif event_type in EventType.corporate_actions():
                accumulator.corporate_action_quantity += txn.quantity

            accumulator.max_quantity = max(accumulator.max_quantity, position_after)
            accumulator.final_quantity = position_after

            decision_type = _decision_type_for(event_type, position_before, position_after)
            accumulator.decision_events.append(
                DecisionEvent(
                    episode_id=0,
                    security_id=txn.security_id,
                    event_date=txn.event_date,
                    decision_type=decision_type.value,
                    quantity_change=txn.quantity,
                    position_before=position_before,
                    position_after=position_after,
                    price=txn.price,
                    source_transaction_id=txn.transaction_id,
                )
            )

            if position_after == 0:
                accumulator.status = EpisodeStatus.CLOSED
                accumulator.exit_date = txn.event_date
                finalize_episode()

        running_quantity = position_after

    finalize_episode()
    session.flush()
    return episodes, all_decision_events
