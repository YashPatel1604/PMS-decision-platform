"""Orchestrate cutover reconciliation across domains."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from pms_platform.reconciliation.compare import (
    compare_bhav_bars,
    compare_charts_range_rows,
    compare_client_book_settings,
    compare_client_positions,
    compare_pivot_portfolio_symbols,
    compare_securities,
    compare_watchlist_members,
)
from pms_platform.reconciliation.manifest import research_file_manifest
from pms_platform.reconciliation.research_compare import compare_research_masters
from pms_platform.reconciliation.types import ReconReport


def run_cutover_reconciliation(
    samir: Session,
    julesh: Session,
    *,
    research_dir: Path | None = None,
    samir_label: str = "samir",
    julesh_label: str = "julesh",
) -> ReconReport:
    """Compare two read-only DB snapshots. Does not modify any source."""
    report = ReconReport(
        generated_at=datetime.now(UTC).isoformat(),
        manifest={
            "samir_label": samir_label,
            "julesh_label": julesh_label,
            "research_dir": str(research_dir) if research_dir else None,
            "research_files": research_file_manifest(research_dir),
        },
    )
    domains = [
        ("client_positions", lambda s, j: compare_client_positions(s, j)),
        ("client_book_settings", lambda s, j: compare_client_book_settings(s, j)),
        ("securities", lambda s, j: compare_securities(s, j)),
        ("watchlist_members", lambda s, j: compare_watchlist_members(s, j)),
        ("charts_range_rows", lambda s, j: compare_charts_range_rows(s, j)),
        ("pivot_portfolio_symbols", lambda s, j: compare_pivot_portfolio_symbols(s, j)),
        ("nse_bhav_bars", lambda s, j: compare_bhav_bars(s, j)),
    ]
    for name, fn in domains:
        report.add_rows(name, fn(samir, julesh))
    if research_dir is not None:
        report.add_rows("research_masters", compare_research_masters(research_dir, samir, julesh))
    return report
