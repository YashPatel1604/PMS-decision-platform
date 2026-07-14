"""Export helpers for episodes and decision events."""

import csv
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.ingestion.validators import ValidationIssue
from pms_platform.models import DecisionEvent, InvestmentEpisode


def export_episodes_csv(session: Session, path: Path) -> None:
    """Export investment episodes to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    episodes = session.scalars(
        select(InvestmentEpisode).order_by(
            InvestmentEpisode.security_id,
            InvestmentEpisode.episode_number,
        )
    ).all()

    fieldnames = [
        "episode_id",
        "security_id",
        "episode_number",
        "entry_date",
        "exit_date",
        "status",
        "initial_quantity",
        "total_buy_quantity",
        "total_sell_quantity",
        "corporate_action_quantity",
        "max_quantity",
        "final_quantity",
        "number_of_buys",
        "number_of_sells",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for episode in episodes:
            writer.writerow(
                {
                    "episode_id": episode.episode_id,
                    "security_id": episode.security_id,
                    "episode_number": episode.episode_number,
                    "entry_date": episode.entry_date.isoformat(),
                    "exit_date": episode.exit_date.isoformat() if episode.exit_date else "",
                    "status": episode.status,
                    "initial_quantity": episode.initial_quantity,
                    "total_buy_quantity": episode.total_buy_quantity,
                    "total_sell_quantity": episode.total_sell_quantity,
                    "corporate_action_quantity": episode.corporate_action_quantity,
                    "max_quantity": episode.max_quantity,
                    "final_quantity": episode.final_quantity,
                    "number_of_buys": episode.number_of_buys,
                    "number_of_sells": episode.number_of_sells,
                }
            )


def export_decision_events_csv(session: Session, path: Path) -> None:
    """Export decision events to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    events = session.scalars(
        select(DecisionEvent).order_by(
            DecisionEvent.security_id,
            DecisionEvent.event_date,
            DecisionEvent.decision_event_id,
        )
    ).all()

    fieldnames = [
        "decision_event_id",
        "episode_id",
        "security_id",
        "event_date",
        "decision_type",
        "quantity_change",
        "position_before",
        "position_after",
        "price",
        "source_transaction_id",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for event in events:
            writer.writerow(
                {
                    "decision_event_id": event.decision_event_id,
                    "episode_id": event.episode_id,
                    "security_id": event.security_id,
                    "event_date": event.event_date.isoformat(),
                    "decision_type": event.decision_type,
                    "quantity_change": event.quantity_change,
                    "position_before": event.position_before,
                    "position_after": event.position_after,
                    "price": event.price,
                    "source_transaction_id": event.source_transaction_id,
                }
            )


def export_validation_report_csv(issues: list[ValidationIssue], path: Path) -> None:
    """Export validation findings to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["severity", "code", "message", "security_id", "source_key", "event_date"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for issue in issues:
            writer.writerow(
                {
                    "severity": issue.severity.value,
                    "code": issue.code,
                    "message": issue.message,
                    "security_id": issue.security_id or "",
                    "source_key": issue.source_key or "",
                    "event_date": issue.event_date.isoformat() if issue.event_date else "",
                }
            )
