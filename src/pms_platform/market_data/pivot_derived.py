"""Derived Last20 window, volume ranks, floor pivots, and gainers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable

_FOUR = Decimal("0.0001")
_TWO = Decimal("0.01")
_BAND = Decimal("0.003")  # 0.3% — matches Excel Sx-0.3 / Rx+0.3


def _q(value: Decimal, places: Decimal = _FOUR) -> Decimal:
    return value.quantize(places, rounding=ROUND_HALF_UP)


def floor_pivot_levels(high: Decimal, low: Decimal, close: Decimal) -> dict[str, Decimal]:
    """Classic floor pivots (incl. S4/R4) + 0.3% bands from the Excel workbook.

    Uses full Decimal precision (Excel does not round intermediates to 4 dp).
    """
    pp = (high + low + close) / Decimal(3)
    r1 = Decimal(2) * pp - low
    s1 = Decimal(2) * pp - high
    r2 = pp + (high - low)
    s2 = pp - (high - low)
    r3 = high + Decimal(2) * (pp - low)
    s3 = low - Decimal(2) * (high - pp)
    r4 = high + Decimal(3) * (pp - low)
    s4 = low - Decimal(3) * (high - pp)
    return {
        "pp": pp,
        "r1": r1,
        "r2": r2,
        "r3": r3,
        "r4": r4,
        "s1": s1,
        "s2": s2,
        "s3": s3,
        "s4": s4,
        # Excel: Sx-0.3 = Sx - Sx*0.3%; Rx+0.3 = Rx + Rx*0.3%
        "s4_03": s4 * (Decimal(1) - _BAND),
        "s3_03": s3 * (Decimal(1) - _BAND),
        "s2_03": s2 * (Decimal(1) - _BAND),
        "s1_03": s1 * (Decimal(1) - _BAND),
        "r1_03": r1 * (Decimal(1) + _BAND),
        "r2_03": r2 * (Decimal(1) + _BAND),
        "r3_03": r3 * (Decimal(1) + _BAND),
        "r4_03": r4 * (Decimal(1) + _BAND),
    }


_LEVEL_KEYS = (
    "pp",
    "r1",
    "r2",
    "r3",
    "r4",
    "s1",
    "s2",
    "s3",
    "s4",
    "s4_03",
    "s3_03",
    "s2_03",
    "s1_03",
    "r1_03",
    "r2_03",
    "r3_03",
    "r4_03",
)


@dataclass(frozen=True)
class VolumeRank:
    symbol: str
    avg_volume: Decimal
    sum_turnover: Decimal
    rank: int
    avg_volume_plus_10pct: Decimal

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "avg_volume": float(self.avg_volume),
            "sum_turnover": float(self.sum_turnover),
            "rank": self.rank,
            "avg_volume_plus_10pct": float(self.avg_volume_plus_10pct),
        }


@dataclass(frozen=True)
class FloorPivot:
    symbol: str
    series: str
    as_of: date
    prior_date: date | None
    prior_high: Decimal
    prior_low: Decimal
    prior_close: Decimal
    last_close: Decimal | None
    pp: Decimal | None
    r1: Decimal | None
    r2: Decimal | None
    r3: Decimal | None
    r4: Decimal | None
    s1: Decimal | None
    s2: Decimal | None
    s3: Decimal | None
    s4: Decimal | None
    s4_03: Decimal | None
    s3_03: Decimal | None
    s2_03: Decimal | None
    s1_03: Decimal | None
    r1_03: Decimal | None
    r2_03: Decimal | None
    r3_03: Decimal | None
    r4_03: Decimal | None
    missing: bool = False

    def as_dict(self) -> dict[str, Any]:
        def f(value: Decimal | None) -> float | None:
            return float(value) if value is not None else None

        return {
            "symbol": self.symbol,
            "series": self.series,
            "as_of": self.as_of.isoformat(),
            "prior_date": self.prior_date.isoformat() if self.prior_date else None,
            "prior_high": f(self.prior_high) if not self.missing else None,
            "prior_low": f(self.prior_low) if not self.missing else None,
            "prior_close": f(self.prior_close) if not self.missing else None,
            "last_close": f(self.last_close),
            "pp": f(self.pp),
            "r1": f(self.r1),
            "r2": f(self.r2),
            "r3": f(self.r3),
            "r4": f(self.r4),
            "s1": f(self.s1),
            "s2": f(self.s2),
            "s3": f(self.s3),
            "s4": f(self.s4),
            "s4_03": f(self.s4_03),
            "s3_03": f(self.s3_03),
            "s2_03": f(self.s2_03),
            "s1_03": f(self.s1_03),
            "r1_03": f(self.r1_03),
            "r2_03": f(self.r2_03),
            "r3_03": f(self.r3_03),
            "r4_03": f(self.r4_03),
            "missing": self.missing,
            "dist_to_pp_pct": (
                float(_q((self.last_close - self.pp) / self.pp * 100, _TWO))
                if self.last_close is not None and self.pp and self.pp != 0
                else None
            ),
        }


@dataclass(frozen=True)
class GainerRow:
    symbol: str
    series: str
    close: Decimal
    prev_close: Decimal | None
    pct_change: Decimal | None
    volume: int
    turnover: Decimal | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "series": self.series,
            "close": float(self.close),
            "prev_close": float(self.prev_close) if self.prev_close is not None else None,
            "pct_change": float(self.pct_change) if self.pct_change is not None else None,
            "volume": self.volume,
            "turnover": float(self.turnover) if self.turnover is not None else None,
        }


def volume_ranks(
    bars: Iterable[Any],
    *,
    series: str | None = "EQ",
) -> list[VolumeRank]:
    """Average volume + sum turnover over the Last20 bars, ranked by turnover.

    Excel AllSymbols ``AvgQty20Days+x%``: top 50 by turnover get +10%, else +20%.
    Pass ``series=None`` when bars are already EQ-preferred (BE-only names included).
    """
    by_symbol: dict[str, list[Any]] = {}
    for bar in bars:
        if series is not None and getattr(bar, "series", None) != series:
            continue
        by_symbol.setdefault(bar.symbol, []).append(bar)

    scored: list[tuple[str, Decimal, Decimal]] = []
    for symbol, group in by_symbol.items():
        avg_vol = Decimal(sum(int(b.volume or 0) for b in group)) / Decimal(len(group))
        sum_to = sum((b.turnover or Decimal(0)) for b in group)
        scored.append((symbol, _q(avg_vol), _q(sum_to, _TWO)))

    scored.sort(key=lambda item: (-item[2], item[0]))
    out: list[VolumeRank] = []
    for idx, (symbol, avg_vol, sum_to) in enumerate(scored, start=1):
        # ponytail: Excel Top50 → ×1.1; rest → ×1.2 (AllSymbols AvgQty20Days+x%)
        bump = Decimal("1.1") if idx <= 50 else Decimal("1.2")
        out.append(
            VolumeRank(
                symbol=symbol,
                avg_volume=avg_vol,
                sum_turnover=sum_to,
                rank=idx,
                avg_volume_plus_10pct=_q(avg_vol * bump),
            )
        )
    return out


def _empty_levels() -> dict[str, None]:
    return {key: None for key in _LEVEL_KEYS}


def floor_pivots_for_symbols(
    *,
    as_of: date,
    symbols: list[str],
    prior_bars: dict[str, Any],
    last_bars: dict[str, Any],
    series: str = "EQ",
) -> list[FloorPivot]:
    """Build floor pivots from the as-of day's H/L/C (matches Excel Daily formulas).

    ``prior_bars`` is unused; kept for call-site compatibility.
    """
    del prior_bars  # Excel uses same-row Hgh/Lw/Cls, not the prior session.
    out: list[FloorPivot] = []
    for symbol in symbols:
        bar = last_bars.get(symbol)
        if bar is None:
            out.append(
                FloorPivot(
                    symbol=symbol,
                    series=series,
                    as_of=as_of,
                    prior_date=None,
                    prior_high=Decimal(0),
                    prior_low=Decimal(0),
                    prior_close=Decimal(0),
                    last_close=None,
                    missing=True,
                    **_empty_levels(),
                )
            )
            continue
        levels = floor_pivot_levels(bar.high, bar.low, bar.close)
        out.append(
            FloorPivot(
                symbol=symbol,
                series=series,
                as_of=as_of,
                prior_date=bar.trade_date,
                prior_high=bar.high,
                prior_low=bar.low,
                prior_close=bar.close,
                last_close=bar.close,
                missing=False,
                **levels,
            )
        )
    return out


def gainer_rows(bars: Iterable[Any], *, series: str = "EQ", limit: int = 200) -> list[GainerRow]:
    """Day's EQ bars ranked by % change vs prev_close."""
    rows: list[GainerRow] = []
    for bar in bars:
        if getattr(bar, "series", None) != series:
            continue
        pct: Decimal | None = None
        if bar.prev_close and bar.prev_close != 0:
            pct = _q((bar.close - bar.prev_close) / bar.prev_close * 100, _TWO)
        rows.append(
            GainerRow(
                symbol=bar.symbol,
                series=bar.series,
                close=bar.close,
                prev_close=bar.prev_close,
                pct_change=pct,
                volume=int(bar.volume or 0),
                turnover=bar.turnover,
            )
        )
    rows.sort(key=lambda r: (r.pct_change is None, -(r.pct_change or Decimal(0))))
    return rows[:limit]
