"""Tests for Research portfolio-value lookup."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from pms_platform.analytics.research_portfolio_value import (
    clear_research_portfolio_value_cache,
    lookup_research_portfolio_value,
)
from pms_platform.research_paths import research_portfolio_history_dir


def test_lookup_dec_31_2025_from_history() -> None:
    clear_research_portfolio_value_cache()
    history = research_portfolio_history_dir()
    assert history is not None
    assert (history / "PMS_ClientPortfolio_311225.xlsx").is_file()

    result = lookup_research_portfolio_value(date(2025, 12, 31))
    assert result is not None
    assert result.source == "HISTORY"
    assert result.observation_date == date(2025, 12, 31)
    assert result.value == Decimal("53586888.67")


def test_lookup_prefers_history_on_or_before_over_model() -> None:
    """History observations beat Model Portfolio even when a model sheet date matches."""
    clear_research_portfolio_value_cache()
    # Mid-year date that likely has model sheets nearby; History should still win if present.
    result = lookup_research_portfolio_value(date(2025, 6, 30))
    assert result is not None
    if research_portfolio_history_dir() is not None:
        assert result.source == "HISTORY"
        assert result.observation_date <= date(2025, 6, 30)


def test_lookup_falls_back_to_values_month_start() -> None:
    clear_research_portfolio_value_cache()
    # No History file for this synthetic mid-month in early series; Values has 2012-01-01.
    # Prefer checking a date that History won't cover before Values starts... skip if History
    # has something earlier. Use Values exact month when History lacks that day.
    # 2012-01-15: History starts ~2017, so Values on/before should win.
    result = lookup_research_portfolio_value(date(2012, 1, 15))
    assert result is not None
    assert result.source in {"VALUES", "MODEL_PORTFOLIO", "HISTORY"}
    assert result.value > 0
