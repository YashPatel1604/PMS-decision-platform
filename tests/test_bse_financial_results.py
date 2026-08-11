"""Tests for BSE financial results parsing."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from pms_platform.market_data.bse_financial_results import parse_results_snapshot

FIXTURE = Path("tests/fixtures/market_data/bse/results_snapshot.json")


def test_parse_results_snapshot_quarterly_only() -> None:
    payload = json.loads(FIXTURE.read_text())
    snapshot = parse_results_snapshot("543320", payload)

    assert snapshot.bse_code == "543320"
    assert snapshot.currency_unit == "in Cr."
    assert len(snapshot.quarters) == 2

    dec = snapshot.quarters[1]
    assert dec.period_label == "Dec-25"
    assert dec.period_end_date.isoformat() == "2025-12-31"
    assert dec.fiscal_quarter == "Q3"
    assert dec.sales == Decimal("2883.00")
    assert dec.pat == Decimal("657.00")
    assert dec.opm == Decimal("27.89")
    assert dec.npm == Decimal("22.79")
