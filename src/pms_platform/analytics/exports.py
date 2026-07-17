"""CSV and Excel exports for episode analytics."""

from __future__ import annotations

import csv
from pathlib import Path

from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.models import (
    EpisodeCashFlowRecord,
    EpisodePerformance,
    PostExitPerformance,
    Security,
    SellAssessment,
)


def _write_sheet(workbook: Workbook, title: str, fieldnames: list[str], rows: list[dict]) -> None:
    sheet = workbook.create_sheet(title=title)
    sheet.append(fieldnames)
    for row in rows:
        sheet.append([row.get(name, "") for name in fieldnames])


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
        "portfolio_return_pct",
        "portfolio_annualized_return",
        "excess_vs_portfolio",
        "smallcap_return_pct",
        "smallcap_annualized_return",
        "excess_vs_smallcap",
        "max_drawdown",
        "max_unrealized_gain",
        "days_below_cost",
        "days_underperforming_benchmark",
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
                    "portfolio_return_pct": row.portfolio_return_pct,
                    "portfolio_annualized_return": row.portfolio_annualized_return,
                    "excess_vs_portfolio": row.excess_vs_portfolio,
                    "smallcap_return_pct": row.smallcap_return_pct,
                    "smallcap_annualized_return": row.smallcap_annualized_return,
                    "excess_vs_smallcap": row.excess_vs_smallcap,
                    "max_drawdown": row.max_drawdown,
                    "max_unrealized_gain": row.max_unrealized_gain,
                    "days_below_cost": row.days_below_cost,
                    "days_underperforming_benchmark": row.days_underperforming_benchmark,
                    "benchmark_code": row.benchmark_code,
                    "benchmark_start_level": row.benchmark_start_level,
                    "benchmark_end_level": row.benchmark_end_level,
                    "calculation_version": row.calculation_version,
                    "data_quality_status": row.data_quality_status,
                    "data_quality_notes": row.data_quality_notes or "",
                }
            )


def export_post_exit_performance_csv(session: Session, path: Path) -> None:
    """Export post-exit performance metrics."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = session.scalars(
        select(PostExitPerformance).order_by(
            PostExitPerformance.episode_id,
        )
    ).all()
    fieldnames = [
        "episode_id",
        "exit_date",
        "comparison_date",
        "security_return_after_exit",
        "portfolio_return_after_exit",
        "smallcap_return_after_exit",
        "excess_vs_portfolio_after_exit",
        "excess_vs_smallcap_after_exit",
        "maximum_gain_after_exit",
        "maximum_loss_after_exit",
        "calculation_version",
        "data_quality_status",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "episode_id": row.episode_id,
                    "exit_date": row.exit_date.isoformat(),
                    "comparison_date": (
                        row.comparison_date.isoformat() if row.comparison_date else ""
                    ),
                    "security_return_after_exit": row.security_return_after_exit,
                    "portfolio_return_after_exit": row.portfolio_return_after_exit,
                    "smallcap_return_after_exit": row.smallcap_return_after_exit,
                    "excess_vs_portfolio_after_exit": row.excess_vs_portfolio_after_exit,
                    "excess_vs_smallcap_after_exit": row.excess_vs_smallcap_after_exit,
                    "maximum_gain_after_exit": row.maximum_gain_after_exit,
                    "maximum_loss_after_exit": row.maximum_loss_after_exit,
                    "calculation_version": row.calculation_version,
                    "data_quality_status": row.data_quality_status,
                }
            )


def export_sell_assessments_csv(session: Session, path: Path) -> None:
    """Export sell-quality assessments."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = session.scalars(select(SellAssessment).order_by(SellAssessment.episode_id)).all()
    fieldnames = [
        "episode_id",
        "exit_assessment",
        "assessment_reason",
        "calculation_version",
        "data_quality_status",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "episode_id": row.episode_id,
                    "exit_assessment": row.exit_assessment,
                    "assessment_reason": row.assessment_reason,
                    "calculation_version": row.calculation_version,
                    "data_quality_status": row.data_quality_status,
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


def export_sell_since_workbook(session: Session, path: Path) -> None:
    """Export a multi-sheet Excel workbook replacing the manual Sell Since report."""
    path.parent.mkdir(parents=True, exist_ok=True)
    securities = {row.security_id: row for row in session.scalars(select(Security)).all()}

    performance_rows = session.scalars(
        select(EpisodePerformance).order_by(
            EpisodePerformance.security_id,
            EpisodePerformance.entry_date,
        )
    ).all()
    post_exit_rows = session.scalars(
        select(PostExitPerformance).order_by(PostExitPerformance.episode_id)
    ).all()
    assessment_rows = session.scalars(select(SellAssessment).order_by(SellAssessment.episode_id)).all()
    cash_flow_rows = session.scalars(
        select(EpisodeCashFlowRecord).order_by(
            EpisodeCashFlowRecord.episode_id,
            EpisodeCashFlowRecord.flow_date,
        )
    ).all()

    workbook = Workbook()
    default_sheet = workbook.active
    if default_sheet is not None:
        workbook.remove(default_sheet)

    performance_payload = [
        {
            "episode_id": row.episode_id,
            "security_id": row.security_id,
            "portfolio_name": securities.get(row.security_id).portfolio_name
            if securities.get(row.security_id)
            else "",
            "entry_date": row.entry_date.isoformat(),
            "exit_date": row.exit_date.isoformat(),
            "holding_days": row.holding_days,
            "total_invested": float(row.total_invested),
            "total_sale_proceeds": float(row.total_sale_proceeds),
            "dividends_received": float(row.dividends_received),
            "total_profit_loss": float(row.total_profit_loss),
            "total_return_pct": float(row.total_return_pct) if row.total_return_pct else "",
            "stock_xirr": float(row.stock_xirr) if row.stock_xirr else "",
            "portfolio_return_pct": float(row.portfolio_return_pct)
            if row.portfolio_return_pct
            else "",
            "excess_vs_portfolio": float(row.excess_vs_portfolio)
            if row.excess_vs_portfolio
            else "",
            "smallcap_return_pct": float(row.smallcap_return_pct)
            if row.smallcap_return_pct
            else "",
            "excess_vs_smallcap": float(row.excess_vs_smallcap)
            if row.excess_vs_smallcap
            else "",
            "max_drawdown": float(row.max_drawdown) if row.max_drawdown else "",
            "days_below_cost": row.days_below_cost,
            "days_underperforming_benchmark": row.days_underperforming_benchmark,
            "data_quality_status": row.data_quality_status,
        }
        for row in performance_rows
    ]
    _write_sheet(
        workbook,
        "episode_performance",
        list(performance_payload[0].keys()) if performance_payload else ["episode_id"],
        performance_payload,
    )

    post_exit_payload = [
        {
            "episode_id": row.episode_id,
            "exit_date": row.exit_date.isoformat(),
            "comparison_date": row.comparison_date.isoformat() if row.comparison_date else "",
            "security_return_after_exit": float(row.security_return_after_exit)
            if row.security_return_after_exit is not None
            else "",
            "portfolio_return_after_exit": float(row.portfolio_return_after_exit)
            if row.portfolio_return_after_exit is not None
            else "",
            "smallcap_return_after_exit": float(row.smallcap_return_after_exit)
            if row.smallcap_return_after_exit is not None
            else "",
            "maximum_gain_after_exit": float(row.maximum_gain_after_exit)
            if row.maximum_gain_after_exit is not None
            else "",
            "maximum_loss_after_exit": float(row.maximum_loss_after_exit)
            if row.maximum_loss_after_exit is not None
            else "",
            "data_quality_status": row.data_quality_status,
        }
        for row in post_exit_rows
    ]
    _write_sheet(
        workbook,
        "post_exit_performance",
        list(post_exit_payload[0].keys()) if post_exit_payload else ["episode_id"],
        post_exit_payload,
    )

    assessment_payload = [
        {
            "episode_id": row.episode_id,
            "exit_assessment": row.exit_assessment,
            "assessment_reason": row.assessment_reason,
            "data_quality_status": row.data_quality_status,
        }
        for row in assessment_rows
    ]
    _write_sheet(
        workbook,
        "sell_assessments",
        list(assessment_payload[0].keys()) if assessment_payload else ["episode_id"],
        assessment_payload,
    )

    cash_flow_payload = [
        {
            "episode_id": row.episode_id,
            "flow_date": row.flow_date.isoformat(),
            "amount": float(row.amount),
            "flow_type": row.flow_type,
            "source": row.source,
        }
        for row in cash_flow_rows
    ]
    _write_sheet(
        workbook,
        "episode_cash_flows",
        list(cash_flow_payload[0].keys()) if cash_flow_payload else ["episode_id"],
        cash_flow_payload,
    )

    workbook.save(path)
