"""Market-data coverage reporting."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pms_platform.market_data.contracts import REQUIRED_BENCHMARKS
from pms_platform.market_data.lookup import lookup_benchmark_tri, lookup_daily_price
from pms_platform.models import BenchmarkTri, DailyPrice, InvestmentEpisode, Security


@dataclass(frozen=True)
class PriceCoverageRow:
    """Coverage status for one security/date requirement."""

    security_id: str
    portfolio_name: str
    requirement_type: str
    required_date: date
    available_date: date | None
    lookup_mode: str | None
    quality_status: str
    notes: str | None = None


@dataclass(frozen=True)
class BenchmarkCoverageRow:
    """Coverage status for one benchmark/date requirement."""

    benchmark_code: str
    requirement_type: str
    required_date: date
    available_date: date | None
    lookup_mode: str | None
    quality_status: str
    notes: str | None = None


def build_price_coverage_report(session: Session) -> list[PriceCoverageRow]:
    """Build episode-driven price coverage findings."""
    episodes = session.scalars(select(InvestmentEpisode)).all()
    securities = {
        security.security_id: security for security in session.scalars(select(Security)).all()
    }
    rows: list[PriceCoverageRow] = []

    for episode in episodes:
        security = securities.get(episode.security_id)
        portfolio_name = security.portfolio_name if security else episode.security_id
        requirements = [
            ("ENTRY", episode.entry_date),
        ]
        if episode.exit_date is not None:
            requirements.extend(
                [
                    ("EXIT", episode.exit_date),
                    ("POST_EXIT_30D", episode.exit_date + timedelta(days=30)),
                    ("POST_EXIT_90D", episode.exit_date + timedelta(days=90)),
                    ("POST_EXIT_180D", episode.exit_date + timedelta(days=180)),
                    ("POST_EXIT_365D", episode.exit_date + timedelta(days=365)),
                ]
            )

        for requirement_type, required_date in requirements:
            observation = lookup_daily_price(session, episode.security_id, required_date)
            if observation is None:
                rows.append(
                    PriceCoverageRow(
                        security_id=episode.security_id,
                        portfolio_name=portfolio_name,
                        requirement_type=requirement_type,
                        required_date=required_date,
                        available_date=None,
                        lookup_mode=None,
                        quality_status="INSUFFICIENT",
                        notes="No price on or before required date",
                    )
                )
                continue

            rows.append(
                PriceCoverageRow(
                    security_id=episode.security_id,
                    portfolio_name=portfolio_name,
                    requirement_type=requirement_type,
                    required_date=required_date,
                    available_date=observation.trade_date,
                    lookup_mode=observation.lookup_mode,
                    quality_status="OK",
                )
            )

    return rows


def build_benchmark_coverage_report(session: Session) -> list[BenchmarkCoverageRow]:
    """Build episode-driven benchmark coverage findings."""
    episodes = session.scalars(select(InvestmentEpisode)).all()
    rows: list[BenchmarkCoverageRow] = []

    for benchmark_code in REQUIRED_BENCHMARKS:
        for episode in episodes:
            requirements = [("ENTRY", episode.entry_date)]
            if episode.exit_date is not None:
                requirements.append(("EXIT", episode.exit_date))

            for requirement_type, required_date in requirements:
                observation = lookup_benchmark_tri(session, benchmark_code, required_date)
                if observation is None:
                    rows.append(
                        BenchmarkCoverageRow(
                            benchmark_code=benchmark_code,
                            requirement_type=requirement_type,
                            required_date=required_date,
                            available_date=None,
                            lookup_mode=None,
                            quality_status="INSUFFICIENT",
                            notes="No TRI level on or before required date",
                        )
                    )
                    continue

                rows.append(
                    BenchmarkCoverageRow(
                        benchmark_code=benchmark_code,
                        requirement_type=requirement_type,
                        required_date=required_date,
                        available_date=observation.trade_date,
                        lookup_mode=observation.lookup_mode,
                        quality_status="OK",
                    )
                )

    return rows


def summarize_price_inventory(session: Session) -> list[dict[str, object]]:
    """Summarize available daily price ranges by security."""
    rows = session.execute(
        select(
            DailyPrice.security_id,
            func.min(DailyPrice.trade_date),
            func.max(DailyPrice.trade_date),
            func.count(),
        ).group_by(DailyPrice.security_id)
    ).all()
    securities = {
        security.security_id: security for security in session.scalars(select(Security)).all()
    }
    summary: list[dict[str, object]] = []
    for security_id, min_date, max_date, count in rows:
        security = securities.get(security_id)
        summary.append(
            {
                "security_id": security_id,
                "portfolio_name": security.portfolio_name if security else None,
                "first_trade_date": min_date,
                "last_trade_date": max_date,
                "observation_count": count,
            }
        )
    return summary


def summarize_benchmark_inventory(session: Session) -> list[dict[str, object]]:
    """Summarize available benchmark TRI ranges."""
    rows = session.execute(
        select(
            BenchmarkTri.benchmark_code,
            func.min(BenchmarkTri.trade_date),
            func.max(BenchmarkTri.trade_date),
            func.count(),
        ).group_by(BenchmarkTri.benchmark_code)
    ).all()
    return [
        {
            "benchmark_code": benchmark_code,
            "first_trade_date": min_date,
            "last_trade_date": max_date,
            "observation_count": count,
        }
        for benchmark_code, min_date, max_date, count in rows
    ]


def export_price_coverage_report(rows: list[PriceCoverageRow], path: Path) -> None:
    """Write price coverage findings to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "security_id",
                "portfolio_name",
                "requirement_type",
                "required_date",
                "available_date",
                "lookup_mode",
                "quality_status",
                "notes",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "security_id": row.security_id,
                    "portfolio_name": row.portfolio_name,
                    "requirement_type": row.requirement_type,
                    "required_date": row.required_date.isoformat(),
                    "available_date": row.available_date.isoformat() if row.available_date else "",
                    "lookup_mode": row.lookup_mode or "",
                    "quality_status": row.quality_status,
                    "notes": row.notes or "",
                }
            )


def export_benchmark_coverage_report(rows: list[BenchmarkCoverageRow], path: Path) -> None:
    """Write benchmark coverage findings to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "benchmark_code",
                "requirement_type",
                "required_date",
                "available_date",
                "lookup_mode",
                "quality_status",
                "notes",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "benchmark_code": row.benchmark_code,
                    "requirement_type": row.requirement_type,
                    "required_date": row.required_date.isoformat(),
                    "available_date": row.available_date.isoformat() if row.available_date else "",
                    "lookup_mode": row.lookup_mode or "",
                    "quality_status": row.quality_status,
                    "notes": row.notes or "",
                }
            )
