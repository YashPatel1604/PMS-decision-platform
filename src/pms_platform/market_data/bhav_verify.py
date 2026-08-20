"""Validate and reconcile NSE bhav rows / derived artifacts."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from pms_platform.market_data.nse_bhav_parse import ParsedBhavRow
from pms_platform.market_data.pivot_derived import FloorPivot, VolumeRank


@dataclass
class ValidationReport:
    ok: bool
    trade_date: date | None
    row_count_all: int = 0
    row_count_eq: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "trade_date": self.trade_date.isoformat() if self.trade_date else None,
            "row_count_all": self.row_count_all,
            "row_count_eq": self.row_count_eq,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


@dataclass
class ReconcileReport:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "checks": dict(self.checks),
        }


def validate_parsed_rows(rows: list[ParsedBhavRow]) -> ValidationReport:
    """Pre-commit checks: single day, OHLC invariants, no duplicate keys."""
    report = ValidationReport(ok=True, trade_date=None)
    if not rows:
        report.ok = False
        report.errors.append("No rows to validate")
        return report

    dates = {row.trade_date for row in rows}
    if len(dates) != 1:
        report.ok = False
        report.errors.append(
            f"Bhav file must contain a single TradDt; found {sorted(d.isoformat() for d in dates)}"
        )
    else:
        report.trade_date = next(iter(dates))

    report.row_count_all = len(rows)
    report.row_count_eq = sum(1 for row in rows if row.series == "EQ")
    if report.row_count_eq == 0:
        report.ok = False
        report.errors.append("No EQ series rows in bhav file")

    keys = Counter((row.symbol, row.series) for row in rows)
    dups = [f"{sym}|{ser}" for (sym, ser), n in keys.items() if n > 1]
    if dups:
        report.ok = False
        report.errors.append(f"Duplicate symbol/series: {', '.join(dups[:10])}")

    for row in rows:
        if row.low > row.high:
            report.ok = False
            report.errors.append(f"{row.symbol}: low > high")
        if min(row.open, row.high, row.low, row.close) <= 0:
            report.ok = False
            report.errors.append(f"{row.symbol}: non-positive price")
        # NSE UDiFF occasionally prints open/close slightly outside H/L; warn only.
        if row.open < row.low or row.open > row.high:
            report.warnings.append(f"{row.symbol}: open outside high/low")
        if row.close < row.low or row.close > row.high:
            report.warnings.append(f"{row.symbol}: close outside high/low")
        if row.prev_close and row.prev_close > 0 and row.close > 0:
            gap = abs(row.close - row.prev_close) / row.prev_close
            if gap >= Decimal("0.25"):
                report.warnings.append(
                    f"{row.symbol}: close vs prev_close gap {float(gap):.0%}"
                )

    # Cap error list size for API payload.
    if len(report.errors) > 50:
        extra = len(report.errors) - 50
        report.errors = report.errors[:50] + [f"…and {extra} more errors"]
    if len(report.warnings) > 30:
        report.warnings = report.warnings[:30] + ["…more warnings truncated"]
    return report


def reconcile_day(
    *,
    expected_all: int,
    expected_eq: int,
    stored_all: int,
    stored_eq: int,
    session_dates: list[date],
    as_of: date,
    ranks: list[VolumeRank],
    pivots: list[FloorPivot],
    portfolio_a_symbols: list[str],
) -> ReconcileReport:
    """Post-commit cross-checks against stored counts and derived artifacts."""
    report = ReconcileReport(ok=True)
    if stored_all != expected_all:
        report.ok = False
        report.errors.append(f"row_count_all mismatch: db={stored_all} expected={expected_all}")
    if stored_eq != expected_eq:
        report.ok = False
        report.errors.append(f"row_count_eq mismatch: db={stored_eq} expected={expected_eq}")

    if not session_dates:
        report.ok = False
        report.errors.append("No session dates after commit")
    elif session_dates[-1] != as_of:
        report.ok = False
        report.errors.append(
            f"Last20 window must end at as_of={as_of}; ends at {session_dates[-1]}"
        )
    if len(session_dates) > 20:
        report.ok = False
        report.errors.append(f"Last20 has {len(session_dates)} sessions (max 20)")

    ranks_sorted = sorted(ranks, key=lambda r: r.rank)
    expected_ranks = list(range(1, len(ranks_sorted) + 1))
    actual_ranks = [r.rank for r in ranks_sorted]
    if actual_ranks != expected_ranks:
        report.ok = False
        report.errors.append("Volume ranks are not dense 1..N")

    for rank in ranks_sorted[:5]:
        expected = (rank.avg_volume * Decimal("1.1")).quantize(Decimal("0.0001"))
        if abs(rank.avg_volume_plus_10pct - expected) > Decimal("0.01"):
            report.ok = False
            report.errors.append(f"{rank.symbol}: avg_volume_plus_10pct mismatch")
            break

    pivot_by_symbol = {p.symbol: p for p in pivots if not p.missing}
    for symbol in portfolio_a_symbols:
        pivot = pivot_by_symbol.get(symbol)
        if pivot is None:
            report.warnings.append(f"PortfolioA {symbol}: pivot_missing (no prior bar)")
            continue
        # Recompute PP/R1/S1 from prior H/L/C.
        from pms_platform.market_data.pivot_derived import floor_pivot_levels

        check = floor_pivot_levels(pivot.prior_high, pivot.prior_low, pivot.prior_close)
        if (
            check["pp"] != pivot.pp
            or check["r1"] != pivot.r1
            or check["s1"] != pivot.s1
        ):
            report.ok = False
            report.errors.append(f"{symbol}: pivot math mismatch")

    report.checks = {
        "stored_all": stored_all,
        "stored_eq": stored_eq,
        "session_count": len(session_dates),
        "rank_count": len(ranks),
        "pivot_ready": sum(1 for p in pivots if not p.missing),
        "pivot_missing": sum(1 for p in pivots if p.missing),
    }
    return report
