"""Export helpers for episodes and decision events."""

import csv
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.ingestion.validators import ValidationIssue
from pms_platform.models import DecisionEvent, InvestmentEpisode
from pms_platform.portfolio.types import LiquidPosition, PortfolioPosition, ReconciliationMismatch


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


def export_portfolio_csv(
    positions: list[PortfolioPosition],
    liquid: LiquidPosition | None,
    path: Path,
) -> None:
    """Export reconstructed portfolio holdings to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "holding_type",
        "security_id",
        "portfolio_name",
        "quantity",
        "cost_basis",
        "market_price",
        "market_value",
        "portfolio_weight",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for position in positions:
            writer.writerow(
                {
                    "holding_type": "equity",
                    "security_id": position.security_id,
                    "portfolio_name": position.portfolio_name,
                    "quantity": position.quantity,
                    "cost_basis": position.cost_basis,
                    "market_price": position.market_price,
                    "market_value": position.market_value,
                    "portfolio_weight": position.portfolio_weight,
                }
            )
        if liquid is not None:
            writer.writerow(
                {
                    "holding_type": "liquid",
                    "security_id": "",
                    "portfolio_name": "LiquidCase",
                    "quantity": liquid.quantity,
                    "cost_basis": liquid.cost_basis,
                    "market_price": liquid.market_price,
                    "market_value": liquid.market_value,
                    "portfolio_weight": "",
                }
            )


def export_reconciliation_report_csv(mismatches: list[ReconciliationMismatch], path: Path) -> None:
    """Export snapshot reconciliation mismatches to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "severity",
        "snapshot_date",
        "security_id",
        "portfolio_name",
        "reconstructed_quantity",
        "snapshot_quantity",
        "difference",
        "source_file",
        "source_sheet",
        "message",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for mismatch in mismatches:
            writer.writerow(
                {
                    "severity": mismatch.severity,
                    "snapshot_date": mismatch.snapshot_date.isoformat(),
                    "security_id": mismatch.security_id or "",
                    "portfolio_name": mismatch.portfolio_name,
                    "reconstructed_quantity": mismatch.reconstructed_quantity,
                    "snapshot_quantity": mismatch.snapshot_quantity,
                    "difference": mismatch.difference,
                    "source_file": mismatch.source_file,
                    "source_sheet": mismatch.source_sheet,
                    "message": mismatch.message,
                }
            )
