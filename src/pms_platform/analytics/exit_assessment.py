"""Dimensional, explainable exit-assessment rules."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

_HUNDRED = Decimal("100")
_ONE = Decimal("1")
_DAYS_PER_YEAR = Decimal("365")

# Ownership thresholds
_TWO_YEARS = 730
_THREE_YEARS = 1095
_FIVE_YEARS = 1825
_ANNUALIZED_LAG_PP = Decimal("5")
_UNDERPERFORM_RATIO = Decimal("0.65")
_MEANINGFUL_PEAK_GAIN = Decimal("25")
_PEAK_GIVEBACK = Decimal("25")
_PEAK_TO_EXIT_DAYS = 90
_LONG_UNDERWATER_DAYS = 365
_ABSOLUTE_RETURN_HURDLE = Decimal("12")

# Fixed one-year post-exit thresholds
_DOWNSIDE_AVOIDED = Decimal("-10")
_MISSED_COMPOUNDING_RETURN = Decimal("15")
_MISSED_COMPOUNDING_EXCESS = Decimal("5")
_BENCHMARK_ROTATION_GAP = Decimal("10")


@dataclass(frozen=True)
class ExitAssessmentInput:
    """Evidence used by the dimensional scorecard."""

    ownership_data_status: str
    one_year_data_status: str
    holding_days: int
    stock_annualized_return_pct: Decimal | None
    smallcap_annualized_return_pct: Decimal | None
    days_underperforming_benchmark: int | None
    ownership_trading_days: int | None
    max_unrealized_gain_pct: Decimal | None
    missed_upside_vs_peak_pct: Decimal | None
    peak_to_exit_days: int | None
    continuous_underwater_days: int | None
    one_year_stock_return_pct: Decimal | None
    one_year_smallcap_return_pct: Decimal | None


@dataclass(frozen=True)
class ExitAssessmentResult:
    """Final verdict plus independent evidence dimensions."""

    primary: str
    ownership_flags: tuple[str, ...]
    post_exit_flags: tuple[str, ...]
    flags: tuple[str, ...]
    confidence: str
    reason: str
    evidence: dict[str, str | int | float | None]


def annualized_return_pct(total_return_pct: Decimal, holding_days: int) -> Decimal | None:
    """Convert a holding-period total return into an annualized percentage."""
    if holding_days <= 0:
        return None
    growth = _ONE + (total_return_pct / _HUNDRED)
    if growth <= 0:
        return None
    exponent = _DAYS_PER_YEAR / Decimal(holding_days)
    return ((growth**exponent) - _ONE) * _HUNDRED


def missed_upside_vs_peak_pct(peak_price: Decimal, exit_price: Decimal) -> Decimal | None:
    """Return how far below the in-hold peak the exit price was."""
    if peak_price <= 0 or exit_price <= 0:
        return None
    return ((peak_price - exit_price) / peak_price) * _HUNDRED


def _annualized_lag(data: ExitAssessmentInput) -> Decimal | None:
    if (
        data.stock_annualized_return_pct is None
        or data.smallcap_annualized_return_pct is None
    ):
        return None
    return data.stock_annualized_return_pct - data.smallcap_annualized_return_pct


def _underperformance_ratio(data: ExitAssessmentInput) -> Decimal | None:
    if (
        data.days_underperforming_benchmark is None
        or not data.ownership_trading_days
        or data.ownership_trading_days <= 0
    ):
        return None
    return Decimal(data.days_underperforming_benchmark) / Decimal(
        data.ownership_trading_days
    )


def assess_ownership_discipline(data: ExitAssessmentInput) -> tuple[str, ...]:
    """Return selective pre-exit ownership-discipline signals."""
    flags: list[str] = []
    lag = _annualized_lag(data)
    underperformance_ratio = _underperformance_ratio(data)

    if (
        data.holding_days >= _TWO_YEARS
        and lag is not None
        and lag <= -_ANNUALIZED_LAG_PP
        and underperformance_ratio is not None
        and underperformance_ratio >= _UNDERPERFORM_RATIO
    ):
        flags.append("SUSTAINED_BENCHMARK_LAG")

    if (
        data.max_unrealized_gain_pct is not None
        and data.max_unrealized_gain_pct >= _MEANINGFUL_PEAK_GAIN
        and data.missed_upside_vs_peak_pct is not None
        and data.missed_upside_vs_peak_pct >= _PEAK_GIVEBACK
        and data.peak_to_exit_days is not None
        and data.peak_to_exit_days >= _PEAK_TO_EXIT_DAYS
    ):
        flags.append("PEAK_GIVEBACK")

    if (
        data.continuous_underwater_days is not None
        and data.continuous_underwater_days >= _LONG_UNDERWATER_DAYS
    ):
        flags.append("LONG_UNDERWATER")

    if (
        data.holding_days >= _FIVE_YEARS
        and lag is not None
        and lag <= -_ANNUALIZED_LAG_PP
        and data.stock_annualized_return_pct is not None
        and data.stock_annualized_return_pct < _ABSOLUTE_RETURN_HURDLE
    ):
        flags.append("CAPITAL_ROTATION_MISSED")
    elif (
        data.holding_days >= _THREE_YEARS
        and lag is not None
        and lag <= -_ANNUALIZED_LAG_PP
    ):
        flags.append("ROTATION_REVIEW")

    return tuple(flags)


def assess_one_year_post_exit(data: ExitAssessmentInput) -> tuple[str, ...]:
    """Return mutually exclusive one-year post-exit timing evidence."""
    if data.one_year_data_status != "OK":
        return ()
    stock = data.one_year_stock_return_pct
    smallcap = data.one_year_smallcap_return_pct
    if stock is None or smallcap is None:
        return ()

    excess = stock - smallcap
    if stock <= _DOWNSIDE_AVOIDED:
        return ("DOWNSIDE_AVOIDED",)
    if (
        stock >= _MISSED_COMPOUNDING_RETURN
        and excess >= _MISSED_COMPOUNDING_EXCESS
    ):
        return ("MISSED_COMPOUNDING",)
    if excess <= -_BENCHMARK_ROTATION_GAP:
        return ("BENCHMARK_ROTATION_JUSTIFIED",)
    return ("NO_STRONG_POST_EXIT_SIGNAL",)


def _final_verdict(
    ownership_flags: tuple[str, ...],
    post_exit_flags: tuple[str, ...],
    data: ExitAssessmentInput,
) -> tuple[str, str]:
    if data.ownership_data_status != "OK":
        return "INSUFFICIENT_DATA", "LOW"

    ownership_issue = bool(ownership_flags)
    severe_ownership_issue = (
        "CAPITAL_ROTATION_MISSED" in ownership_flags
        or len(ownership_flags) >= 2
    )

    if data.one_year_data_status == "TOO_RECENT":
        if severe_ownership_issue:
            return "EXIT_TOO_LATE", "LOW"
        return "TOO_RECENT_TO_JUDGE", "LOW"
    if data.one_year_data_status != "OK":
        return "INSUFFICIENT_DATA", "LOW"

    missed_compounding = "MISSED_COMPOUNDING" in post_exit_flags
    timing_supported = bool(
        {"DOWNSIDE_AVOIDED", "BENCHMARK_ROTATION_JUSTIFIED"}
        & set(post_exit_flags)
    )

    if missed_compounding and ownership_issue:
        return "MIXED_EVIDENCE", "MEDIUM"
    if missed_compounding:
        return "EXIT_TOO_EARLY", "HIGH"
    if timing_supported and ownership_issue:
        return "EXIT_TOO_LATE", "HIGH"
    if timing_supported:
        return "WELL_TIMED_EXIT", "HIGH"
    if ownership_issue:
        return "EXIT_TOO_LATE", "MEDIUM"
    return "NO_STRONG_SIGNAL", "MEDIUM"


def _reason(
    verdict: str,
    ownership_flags: tuple[str, ...],
    post_exit_flags: tuple[str, ...],
    data: ExitAssessmentInput,
) -> str:
    parts = [f"Verdict: {verdict.replace('_', ' ').title()}."]
    if ownership_flags:
        parts.append(
            "Ownership evidence: "
            + ", ".join(flag.replace("_", " ").lower() for flag in ownership_flags)
            + "."
        )
    else:
        parts.append("Ownership evidence: no strong discipline failure.")

    if data.one_year_data_status == "TOO_RECENT":
        parts.append("One-year post-exit evidence is not yet available.")
    elif post_exit_flags:
        parts.append(
            "One-year post-exit evidence: "
            + ", ".join(flag.replace("_", " ").lower() for flag in post_exit_flags)
            + "."
        )
    else:
        parts.append("One-year post-exit evidence is insufficient.")
    return " ".join(parts)


def assess_exit_quality(data: ExitAssessmentInput) -> ExitAssessmentResult:
    """Build dimensions first, then derive one deterministic final verdict."""
    ownership_flags = assess_ownership_discipline(data)
    post_exit_flags = assess_one_year_post_exit(data)
    primary, confidence = _final_verdict(ownership_flags, post_exit_flags, data)
    all_flags = (*ownership_flags, *post_exit_flags)
    lag = _annualized_lag(data)
    ratio = _underperformance_ratio(data)
    evidence: dict[str, str | int | float | None] = {
        "holding_days": data.holding_days,
        "stock_annualized_return_pct": (
            float(data.stock_annualized_return_pct)
            if data.stock_annualized_return_pct is not None
            else None
        ),
        "smallcap_annualized_return_pct": (
            float(data.smallcap_annualized_return_pct)
            if data.smallcap_annualized_return_pct is not None
            else None
        ),
        "annualized_lag_pp": float(lag) if lag is not None else None,
        "underperformance_day_ratio": float(ratio) if ratio is not None else None,
        "max_unrealized_gain_pct": (
            float(data.max_unrealized_gain_pct)
            if data.max_unrealized_gain_pct is not None
            else None
        ),
        "missed_upside_vs_peak_pct": (
            float(data.missed_upside_vs_peak_pct)
            if data.missed_upside_vs_peak_pct is not None
            else None
        ),
        "peak_to_exit_days": data.peak_to_exit_days,
        "continuous_underwater_days": data.continuous_underwater_days,
        "one_year_data_status": data.one_year_data_status,
        "one_year_stock_return_pct": (
            float(data.one_year_stock_return_pct)
            if data.one_year_stock_return_pct is not None
            else None
        ),
        "one_year_smallcap_return_pct": (
            float(data.one_year_smallcap_return_pct)
            if data.one_year_smallcap_return_pct is not None
            else None
        ),
    }
    return ExitAssessmentResult(
        primary=primary,
        ownership_flags=ownership_flags,
        post_exit_flags=post_exit_flags,
        flags=all_flags,
        confidence=confidence,
        reason=_reason(primary, ownership_flags, post_exit_flags, data),
        evidence=evidence,
    )
