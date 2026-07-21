"""CSV and Excel exports for episode analytics."""

from __future__ import annotations

import csv
from pathlib import Path

from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.analytics.first_buy_audit import build_first_buy_price_audit
from pms_platform.models import (
    EpisodeCashFlowRecord,
    EpisodePerformance,
    PostExitHorizonPerformance,
    Security,
    SellAssessment,
)


def export_first_buy_price_audit_csv(session: Session, path: Path) -> None:
    """Export consolidated first-buy normalization checks for closed episodes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "episode_id",
        "security_id",
        "portfolio_name",
        "entry_date",
        "initial_purchase_price",
        "entry_market_price",
        "inferred_unit_factor",
        "normalized_first_buy_price",
        "entry_deviation_pct",
        "status",
        "note",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in build_first_buy_price_audit(session):
            writer.writerow(
                {
                    "episode_id": row.episode_id,
                    "security_id": row.security_id,
                    "portfolio_name": row.portfolio_name,
                    "entry_date": row.entry_date.isoformat(),
                    "initial_purchase_price": row.initial_purchase_price,
                    "entry_market_price": row.entry_market_price,
                    "inferred_unit_factor": row.inferred_unit_factor,
                    "normalized_first_buy_price": (
                        row.normalized_first_buy_price
                    ),
                    "entry_deviation_pct": row.entry_deviation_pct,
                    "status": row.status,
                    "note": row.note,
                }
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
        "average_buy_price",
        "average_sell_price",
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
        "peak_price_during_hold",
        "peak_price_date",
        "exit_adjusted_close",
        "missed_upside_vs_peak_pct",
        "days_below_cost",
        "first_below_cost_date",
        "days_held_after_first_loss",
        "calendar_days_held_after_first_loss",
        "loss_hold_pattern",
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
                    "average_buy_price": row.average_buy_price,
                    "average_sell_price": row.average_sell_price,
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
                    "peak_price_during_hold": row.peak_price_during_hold,
                    "peak_price_date": (
                        row.peak_price_date.isoformat() if row.peak_price_date else ""
                    ),
                    "exit_adjusted_close": row.exit_adjusted_close,
                    "missed_upside_vs_peak_pct": row.missed_upside_vs_peak_pct,
                    "days_below_cost": row.days_below_cost,
                    "first_below_cost_date": (
                        row.first_below_cost_date.isoformat()
                        if row.first_below_cost_date
                        else ""
                    ),
                    "days_held_after_first_loss": row.days_held_after_first_loss,
                    "calendar_days_held_after_first_loss": (
                        row.calendar_days_held_after_first_loss
                    ),
                    "loss_hold_pattern": row.loss_hold_pattern or "",
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
    """Export every standardized post-exit horizon."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = session.scalars(
        select(PostExitHorizonPerformance).order_by(
            PostExitHorizonPerformance.episode_id,
            PostExitHorizonPerformance.post_exit_horizon_performance_id,
        )
    ).all()
    fieldnames = [
        "episode_id",
        "horizon",
        "exit_date",
        "target_date",
        "comparison_date",
        "days_after_exit",
        "security_return_after_exit",
        "smallcap_return_after_exit",
        "excess_vs_smallcap_after_exit",
        "provisional_portfolio_return_after_exit",
        "provisional_excess_vs_portfolio_after_exit",
        "portfolio_comparator_status",
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
                    "horizon": row.horizon,
                    "exit_date": row.exit_date.isoformat(),
                    "target_date": row.target_date.isoformat() if row.target_date else "",
                    "comparison_date": (
                        row.comparison_date.isoformat() if row.comparison_date else ""
                    ),
                    "security_return_after_exit": row.security_return_after_exit,
                    "days_after_exit": row.days_after_exit,
                    "smallcap_return_after_exit": row.smallcap_return_after_exit,
                    "excess_vs_smallcap_after_exit": row.excess_vs_smallcap_after_exit,
                    "provisional_portfolio_return_after_exit": (
                        row.provisional_portfolio_return_after_exit
                    ),
                    "provisional_excess_vs_portfolio_after_exit": (
                        row.provisional_excess_vs_portfolio_after_exit
                    ),
                    "portfolio_comparator_status": "PROVISIONAL",
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
        "assessment_flags",
        "ownership_flags",
        "post_exit_flags",
        "assessment_confidence",
        "assessment_reason",
        "assessment_evidence",
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
                    "assessment_flags": row.assessment_flags or "",
                    "ownership_flags": row.ownership_flags or "",
                    "post_exit_flags": row.post_exit_flags or "",
                    "assessment_confidence": row.assessment_confidence or "",
                    "assessment_reason": row.assessment_reason,
                    "assessment_evidence": row.assessment_evidence or "",
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
        select(PostExitHorizonPerformance).order_by(
            PostExitHorizonPerformance.episode_id,
            PostExitHorizonPerformance.post_exit_horizon_performance_id,
        )
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
            "portfolio_name": securities[row.security_id].portfolio_name
            if row.security_id in securities
            else "",
            "entry_date": row.entry_date.isoformat(),
            "exit_date": row.exit_date.isoformat(),
            "holding_days": row.holding_days,
            "average_buy_price": (
                float(row.average_buy_price)
                if row.average_buy_price is not None
                else ""
            ),
            "average_sell_price": (
                float(row.average_sell_price)
                if row.average_sell_price is not None
                else ""
            ),
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
            "max_unrealized_gain": (
                float(row.max_unrealized_gain)
                if row.max_unrealized_gain is not None
                else ""
            ),
            "peak_price_during_hold": (
                float(row.peak_price_during_hold)
                if row.peak_price_during_hold is not None
                else ""
            ),
            "peak_price_date": (
                row.peak_price_date.isoformat() if row.peak_price_date else ""
            ),
            "missed_upside_vs_peak_pct": (
                float(row.missed_upside_vs_peak_pct)
                if row.missed_upside_vs_peak_pct is not None
                else ""
            ),
            "days_below_cost": row.days_below_cost,
            "first_below_cost_date": (
                row.first_below_cost_date.isoformat()
                if row.first_below_cost_date
                else ""
            ),
            "days_held_after_first_loss": row.days_held_after_first_loss,
            "calendar_days_held_after_first_loss": (
                row.calendar_days_held_after_first_loss
            ),
            "loss_hold_pattern": row.loss_hold_pattern or "",
            "days_underperforming_benchmark": row.days_underperforming_benchmark,
            "calculation_version": row.calculation_version,
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
            "horizon": row.horizon,
            "exit_date": row.exit_date.isoformat(),
            "target_date": row.target_date.isoformat() if row.target_date else "",
            "comparison_date": row.comparison_date.isoformat() if row.comparison_date else "",
            "days_after_exit": row.days_after_exit,
            "security_return_after_exit": float(row.security_return_after_exit)
            if row.security_return_after_exit is not None
            else "",
            "smallcap_return_after_exit": float(row.smallcap_return_after_exit)
            if row.smallcap_return_after_exit is not None
            else "",
            "excess_vs_smallcap_after_exit": float(row.excess_vs_smallcap_after_exit)
            if row.excess_vs_smallcap_after_exit is not None
            else "",
            "provisional_portfolio_return_after_exit": float(
                row.provisional_portfolio_return_after_exit
            )
            if row.provisional_portfolio_return_after_exit is not None
            else "",
            "provisional_excess_vs_portfolio_after_exit": float(
                row.provisional_excess_vs_portfolio_after_exit
            )
            if row.provisional_excess_vs_portfolio_after_exit is not None
            else "",
            "portfolio_comparator_status": "PROVISIONAL",
            "calculation_version": row.calculation_version,
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
            "assessment_flags": row.assessment_flags or "",
            "ownership_flags": row.ownership_flags or "",
            "post_exit_flags": row.post_exit_flags or "",
            "assessment_confidence": row.assessment_confidence or "",
            "assessment_reason": row.assessment_reason,
            "assessment_evidence": row.assessment_evidence or "",
            "calculation_version": row.calculation_version,
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
