"""Episode cash-flow construction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.models import DecisionEvent, Dividend, InvestmentEpisode, Transaction
from pms_platform.models.enums import DecisionType, EventType

_ZERO = Decimal("0")


@dataclass(frozen=True)
class EpisodeCashFlow:
    """One dated cash-flow line for an investment episode."""

    episode_id: int
    flow_date: date
    amount: Decimal
    flow_type: str
    source: str
    source_reference: str | None = None


def _transaction_cash_amount(transaction: Transaction) -> Decimal | None:
    """Derive a signed cash amount from a transaction row."""
    if transaction.amount is not None and transaction.amount != 0:
        amount = transaction.amount.copy_abs()
    elif transaction.price is not None and transaction.quantity != 0:
        amount = transaction.price.copy_abs() * Decimal(abs(transaction.quantity))
    else:
        return None

    event_type = EventType.from_workbook(transaction.event_type)
    if event_type in {EventType.BUY, EventType.RIGHTS}:
        return -amount
    if event_type == EventType.SELL:
        return amount
    return None


def _position_on_date(events: list[DecisionEvent], as_of_date: date) -> int:
    position = 0
    for event in events:
        if event.event_date > as_of_date:
            break
        position = event.position_after
    return position


def build_episode_cash_flows(
    session: Session,
    episode: InvestmentEpisode,
    events: list[DecisionEvent],
) -> tuple[list[EpisodeCashFlow], list[str]]:
    """Build dated cash flows and data-quality notes for one episode."""
    flows: list[EpisodeCashFlow] = []
    notes: list[str] = []
    transaction_ids = {
        event.source_transaction_id
        for event in events
        if event.source_transaction_id is not None
    }
    transactions: dict[int, Transaction] = {}
    if transaction_ids:
        rows = session.scalars(
            select(Transaction).where(Transaction.transaction_id.in_(transaction_ids))
        ).all()
        transactions = {row.transaction_id: row for row in rows}

    for event in events:
        if event.decision_type == DecisionType.CORPORATE_ACTION.value:
            transaction = (
                transactions.get(event.source_transaction_id)
                if event.source_transaction_id is not None
                else None
            )
            if transaction is None:
                continue
            event_type = EventType.from_workbook(transaction.event_type)
            if event_type not in {EventType.RIGHTS}:
                continue

        transaction = (
            transactions.get(event.source_transaction_id)
            if event.source_transaction_id is not None
            else None
        )
        if transaction is None:
            notes.append(f"Missing source transaction for decision event on {event.event_date}")
            continue

        amount = _transaction_cash_amount(transaction)
        if amount is None:
            notes.append(
                f"Missing cash amount for {transaction.event_type} on {transaction.event_date}"
            )
            continue

        flow_type = EventType.from_workbook(transaction.event_type).value.upper()
        flows.append(
            EpisodeCashFlow(
                episode_id=episode.episode_id,
                flow_date=event.event_date,
                amount=amount,
                flow_type=flow_type,
                source="TRANSACTION",
                source_reference=str(transaction.transaction_id),
            )
        )

    if episode.exit_date is None:
        return flows, notes

    dividend_rows = session.scalars(
        select(Dividend)
        .where(
            Dividend.security_id == episode.security_id,
            Dividend.ex_date >= episode.entry_date,
            Dividend.ex_date <= episode.exit_date,
        )
        .order_by(Dividend.ex_date)
    ).all()

    for dividend in dividend_rows:
        shares = _position_on_date(events, dividend.ex_date)
        if shares <= 0:
            continue
        flows.append(
            EpisodeCashFlow(
                episode_id=episode.episode_id,
                flow_date=dividend.ex_date,
                amount=dividend.dividend_per_share * Decimal(shares),
                flow_type="DIVIDEND",
                source="DIVIDEND",
                source_reference=str(dividend.dividend_id),
            )
        )

    flows.sort(key=lambda row: (row.flow_date, row.flow_type, row.source_reference or ""))
    return flows, notes
