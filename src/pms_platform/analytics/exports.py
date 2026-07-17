"""CSV exports for episode analytics."""

from __future__ import annotations

import csv
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.models import EpisodeCashFlowRecord, EpisodePerformance, Security


def export_episode_performance_csv(session: Session, path: Path) -> None:
    """Export ownership-period episode performance metrics."""
    path.parent.mkdir(parents=True, exist_ok=True)
    securities = {row.security_id: row for row in session.scalars(select(Security)).all()}
    rows = session.scalars(
        select(EpisodePerformance).order_by(
            EpisodePerformance.security_id,
            EpisodePerformance.entry_date,
        )
    ).all()

    fieldnames = [
        "episode_id",
        "security_id",
        "portfolio_name",
        "entry_date",
        "exit_date",
        "holding_days",
        "total_invested",
        "total_sale_proceeds",
        "dividends_received",
        "total_profit_loss",
        "total_return_pct",
        "stock_xirr",
        "smallcap_return_pct",
        "smallcap_annualized_return",
        "excess_vs_smallcap",
        "benchmark_code",
        "benchmark_start_level",
        "benchmark_end_level",
        "calculation_version",
        "data_quality_status",
        "data_quality_notes",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            security = securities.get(row.security_id)
            writer.writerow(
                {
                    "episode_id": row.episode_id,
                    "security_id": row.security_id,
                    "portfolio_name": security.portfolio_name if security else "",
                    "entry_date": row.entry_date.isoformat(),
                    "exit_date": row.exit_date.isoformat(),
                    "holding_days": row.holding_days,
                    "total_invested": row.total_invested,
                    "total_sale_proceeds": row.total_sale_proceeds,
                    "dividends_received": row.dividends_received,
                    "total_profit_loss": row.total_profit_loss,
                    "total_return_pct": row.total_return_pct,
                    "stock_xirr": row.stock_xirr,
                    "smallcap_return_pct": row.smallcap_return_pct,
                    "smallcap_annualized_return": row.smallcap_annualized_return,
                    "excess_vs_smallcap": row.excess_vs_smallcap,
                    "benchmark_code": row.benchmark_code,
                    "benchmark_start_level": row.benchmark_start_level,
                    "benchmark_end_level": row.benchmark_end_level,
                    "calculation_version": row.calculation_version,
                    "data_quality_status": row.data_quality_status,
                    "data_quality_notes": row.data_quality_notes or "",
                }
            )


def export_episode_cash_flows_csv(session: Session, path: Path) -> None:
    """Export persisted episode cash flows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = session.scalars(
        select(EpisodeCashFlowRecord).order_by(
            EpisodeCashFlowRecord.episode_id,
            EpisodeCashFlowRecord.flow_date,
            EpisodeCashFlowRecord.episode_cash_flow_id,
        )
    ).all()

    fieldnames = [
        "episode_id",
        "flow_date",
        "amount",
        "flow_type",
        "source",
        "source_reference",
        "calculation_version",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "episode_id": row.episode_id,
                    "flow_date": row.flow_date.isoformat(),
                    "amount": row.amount,
                    "flow_type": row.flow_type,
                    "source": row.source,
                    "source_reference": row.source_reference or "",
                    "calculation_version": row.calculation_version,
                }
            )
