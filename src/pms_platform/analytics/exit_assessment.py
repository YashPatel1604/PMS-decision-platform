"""Comprehensive exit-quality assessment rules."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

_HUNDRED = Decimal("100")
_ONE = Decimal("1")
_ZERO = Decimal("0")
_DAYS_PER_YEAR = Decimal("365")

# Post-exit thresholds
_PREMATURE_EXCESS_THRESHOLD = Decimal("15")
_PREMATURE_VS_PORTFOLIO_THRESHOLD = Decimal("10")
_LOSS_AVOIDED_THRESHOLD = Decimal("-10")
_INDEX_BEAT_HOLD_THRESHOLD = Decimal("25")
_PORTFOLIO_BEAT_HOLD_THRESHOLD = Decimal("15")
_LEFT_STOCK_UPSIDE_THRESHOLD = Decimal("20")
_REDEPLOYMENT_LAG_THRESHOLD = Decimal("25")
_GOOD_EXIT_LAG_THRESHOLD = Decimal("10")

# Ownership / rotation thresholds
_LATE_EXIT_EXCESS_THRESHOLD = Decimal("-3")
_LONG_HOLD_DAYS = 2555  # ~7 years
_VERY_LONG_HOLD_DAYS = 3650  # ~10 years
_ROTATION_MIN_ANNUALIZED = Decimal("12")
_VERY_LONG_HOLD_MIN_TOTAL_RETURN = Decimal("200")
_LONG_HOLD_MIN_TOTAL_RETURN = Decimal("150")
_GAVE_BACK_PEAK_THRESHOLD = Decimal("20")
_UNDERPERFORM_DAY_RATIO = Decimal("0.55")


@dataclass(frozen=True)
class ExitAssessmentInput:
    """Inputs required to classify an exit holistically."""

    data_quality_status: str
    holding_days: int
    total_return_pct: Decimal | None
    stock_xirr: Decimal | None
    stock_annualized_return_pct: Decimal | None
    smallcap_return_pct: Decimal | None
    smallcap_annualized_return_pct: Decimal | None
    portfolio_return_pct: Decimal | None
    excess_vs_smallcap: Decimal | None
    excess_vs_portfolio: Decimal | None
    days_underperforming_benchmark: int | None
    ownership_trading_days: int | None
    max_drawdown_pct: Decimal | None
    missed_upside_vs_peak_pct: Decimal | None
    security_return_after_exit: Decimal | None
    portfolio_return_after_exit: Decimal | None
    benchmark_return_after_exit: Decimal | None
    maximum_gain_after_exit: Decimal | None
    maximum_loss_after_exit: Decimal | None


@dataclass(frozen=True)
class ExitAssessmentResult:
    """Assessment outcome with all triggered flags."""

    primary: str
    flags: tuple[str, ...]
    reason: str


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


def _format_hold_context(data: ExitAssessmentInput) -> str | None:
    parts: list[str] = []
    if data.total_return_pct is not None:
        parts.append(f"stock {data.total_return_pct:+.1f}%")
    if data.portfolio_return_pct is not None:
        parts.append(f"portfolio {data.portfolio_return_pct:+.1f}%")
    if data.smallcap_return_pct is not None:
        parts.append(f"BSE SmallCap {data.smallcap_return_pct:+.1f}%")
    if not parts:
        return None
    return "While held: " + ", ".join(parts)


def _format_post_exit_context(data: ExitAssessmentInput) -> str | None:
    parts: list[str] = []
    if data.security_return_after_exit is not None:
        parts.append(f"stock {data.security_return_after_exit:+.1f}%")
    if data.portfolio_return_after_exit is not None:
        parts.append(f"portfolio {data.portfolio_return_after_exit:+.1f}%")
    if data.benchmark_return_after_exit is not None:
        parts.append(f"BSE SmallCap {data.benchmark_return_after_exit:+.1f}%")
    if not parts:
        return None
    return "After exit: " + ", ".join(parts)


def _flag_late_exit(data: ExitAssessmentInput) -> str | None:
    if data.excess_vs_smallcap is not None and data.excess_vs_smallcap <= _LATE_EXIT_EXCESS_THRESHOLD:
        return (
            f"Underperformed BSE SmallCap by {abs(data.excess_vs_smallcap):.1f}% over the hold"
        )
    if data.excess_vs_smallcap is not None and data.excess_vs_smallcap > _ZERO:
        return None
    if (
        data.stock_xirr is not None
        and data.smallcap_annualized_return_pct is not None
        and (data.stock_xirr * _HUNDRED) < data.smallcap_annualized_return_pct - Decimal("2")
    ):
        return (
            f"Stock XIRR {(data.stock_xirr * _HUNDRED):.1f}% trailed small-cap annualized "
            f"{data.smallcap_annualized_return_pct:.1f}%"
        )
    if (
        data.days_underperforming_benchmark is not None
        and data.ownership_trading_days
        and data.ownership_trading_days > 0
        and Decimal(data.days_underperforming_benchmark) / Decimal(data.ownership_trading_days)
        >= _UNDERPERFORM_DAY_RATIO
    ):
        ratio = (
            Decimal(data.days_underperforming_benchmark) / Decimal(data.ownership_trading_days)
        ) * _HUNDRED
        return f"Underperformed benchmark on {ratio:.0f}% of trading days while held"
    return None


def _flag_capital_rotation_missed(data: ExitAssessmentInput) -> str | None:
    ann = data.stock_annualized_return_pct
    bench_ann = data.smallcap_annualized_return_pct
    hurdle = max(_ROTATION_MIN_ANNUALIZED, bench_ann or _ZERO)

    if data.holding_days >= _VERY_LONG_HOLD_DAYS:
        if data.total_return_pct is not None and data.total_return_pct < _VERY_LONG_HOLD_MIN_TOTAL_RETURN:
            return (
                f"Held {data.holding_days // 365} years for only {data.total_return_pct:.0f}% total; "
                "capital likely earned more elsewhere over the same window"
            )
        if ann is not None and ann < hurdle:
            return f"Held {data.holding_days // 365} years at {ann:.1f}% annualized vs {hurdle:.1f}% hurdle"

    if data.holding_days >= _LONG_HOLD_DAYS:
        if ann is not None and ann < hurdle:
            return (
                f"Long {data.holding_days // 365}y hold at {ann:.1f}% annualized "
                f"vs {hurdle:.1f}% rotation hurdle"
            )
        if (
            data.total_return_pct is not None
            and data.total_return_pct < _LONG_HOLD_MIN_TOTAL_RETURN
            and data.excess_vs_smallcap is not None
            and data.excess_vs_smallcap < _ZERO
        ):
            return (
                f"Held {data.holding_days // 365} years for {data.total_return_pct:.0f}% "
                "while lagging small-cap"
            )
    return None


def _flag_gave_back_gains(data: ExitAssessmentInput) -> str | None:
    if (
        data.missed_upside_vs_peak_pct is not None
        and data.missed_upside_vs_peak_pct >= _GAVE_BACK_PEAK_THRESHOLD
    ):
        return f"Sold {data.missed_upside_vs_peak_pct:.1f}% below the in-hold price peak"
    if data.max_drawdown_pct is not None and data.max_drawdown_pct >= Decimal("35"):
        return f"Exit followed a {data.max_drawdown_pct:.1f}% drawdown from the in-hold peak"
    return None


def _evaluate_post_exit(data: ExitAssessmentInput) -> tuple[list[str], list[str]]:
    """Return post-exit flags and detail reasons."""
    flags: list[str] = []
    reasons: list[str] = []

    post = data.security_return_after_exit
    bench_post = data.benchmark_return_after_exit
    portfolio_post = data.portfolio_return_after_exit

    if post is None:
        return flags, reasons

    if (
        data.maximum_loss_after_exit is not None
        and data.maximum_loss_after_exit <= _LOSS_AVOIDED_THRESHOLD
        and post <= _ZERO
    ):
        flags.append("LOSS_AVOIDED")
        reasons.append(
            f"Avoided further decline of up to {data.maximum_loss_after_exit:.1f}% after exit"
        )

    if post >= _LEFT_STOCK_UPSIDE_THRESHOLD:
        flags.append("LEFT_STOCK_UPSIDE")
        reasons.append(f"Stock still rose {post:.1f}% after exit if held")

    if bench_post is not None and bench_post - post >= _INDEX_BEAT_HOLD_THRESHOLD:
        flags.append("INDEX_OUTPERFORMED_HOLD")
        reasons.append(
            f"BSE SmallCap returned {bench_post:.1f}% vs {post:.1f}% if held "
            f"({bench_post - post:.1f}pp better)"
        )

    if (
        portfolio_post is not None
        and portfolio_post - post >= _PORTFOLIO_BEAT_HOLD_THRESHOLD
    ):
        flags.append("PORTFOLIO_OUTPERFORMED_HOLD")
        reasons.append(
            f"Portfolio returned {portfolio_post:.1f}% vs {post:.1f}% if held "
            f"({portfolio_post - post:.1f}pp better)"
        )

    if (
        bench_post is not None
        and portfolio_post is not None
        and bench_post - portfolio_post >= _REDEPLOYMENT_LAG_THRESHOLD
    ):
        flags.append("REDEPLOYMENT_LAG")
        reasons.append(
            f"Portfolio returned {portfolio_post:.1f}% after exit vs BSE SmallCap "
            f"{bench_post:.1f}% ({bench_post - portfolio_post:.1f}pp index gap)"
        )

    beats_benchmark = (
        bench_post is not None and post - bench_post > _PREMATURE_EXCESS_THRESHOLD and post > _ZERO
    )
    beats_portfolio = (
        portfolio_post is None
        or (post - portfolio_post > _PREMATURE_VS_PORTFOLIO_THRESHOLD and post > _ZERO)
    )
    if (
        beats_benchmark
        and beats_portfolio
        and "LATE_EXIT" not in flags
        and "CAPITAL_ROTATION_MISSED" not in flags
    ):
        flags.append("PREMATURE_EXIT")
        portfolio_note = (
            f" vs portfolio {portfolio_post:.1f}%"
            if portfolio_post is not None
            else ""
        )
        reasons.append(
            f"Stock returned {post:.1f}% after exit vs BSE SmallCap {bench_post:.1f}%"
            f"{portfolio_note}"
        )

    lagged_benchmark = bench_post is not None and post < bench_post - _GOOD_EXIT_LAG_THRESHOLD
    lagged_portfolio = portfolio_post is not None and post < portfolio_post - _GOOD_EXIT_LAG_THRESHOLD
    if (
        (post < -Decimal("5") or (lagged_benchmark and lagged_portfolio))
        and "PREMATURE_EXIT" not in flags
    ):
        flags.append("GOOD_EXIT")
        if post < _ZERO:
            reasons.append(f"Stock fell {post:.1f}% after exit")
        else:
            reasons.append(
                f"Sold name returned {post:.1f}% after exit, lagging redeployed capital"
            )

    return flags, reasons


def assess_exit_quality(data: ExitAssessmentInput) -> ExitAssessmentResult:
    """Classify exit quality using ownership and post-exit evidence."""
    if data.data_quality_status != "OK":
        return ExitAssessmentResult(
            primary="INSUFFICIENT_DATA",
            flags=("INSUFFICIENT_DATA",),
            reason="Missing price, benchmark, or post-exit history",
        )

    flags: list[str] = []
    reasons: list[str] = []

    late_reason = _flag_late_exit(data)
    if late_reason:
        flags.append("LATE_EXIT")
        reasons.append(late_reason)

    rotation_reason = _flag_capital_rotation_missed(data)
    if rotation_reason:
        flags.append("CAPITAL_ROTATION_MISSED")
        reasons.append(rotation_reason)

    gave_back_reason = _flag_gave_back_gains(data)
    if gave_back_reason:
        flags.append("GAVE_BACK_GAINS")
        reasons.append(gave_back_reason)

    post_flags, post_reasons = _evaluate_post_exit(data)
    flags.extend(post_flags)
    reasons.extend(post_reasons)

    post_context = _format_post_exit_context(data)
    if post_context and post_context not in reasons:
        reasons.append(post_context)

    if not flags:
        return ExitAssessmentResult(
            primary="NEUTRAL_EXIT",
            flags=("NEUTRAL_EXIT",),
            reason="; ".join(reasons) if reasons else "No strong exit signal",
        )

    priority = (
        "LOSS_AVOIDED",
        "LATE_EXIT",
        "CAPITAL_ROTATION_MISSED",
        "GAVE_BACK_GAINS",
        "PREMATURE_EXIT",
        "LEFT_STOCK_UPSIDE",
        "INDEX_OUTPERFORMED_HOLD",
        "PORTFOLIO_OUTPERFORMED_HOLD",
        "REDEPLOYMENT_LAG",
        "GOOD_EXIT",
    )
    primary = next((label for label in priority if label in flags), flags[0])
    return ExitAssessmentResult(primary=primary, flags=tuple(flags), reason="; ".join(reasons))
