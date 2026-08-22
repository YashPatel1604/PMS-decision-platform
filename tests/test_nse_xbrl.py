"""Tests for NSE financial XBRL parsing."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from pms_platform.fundamentals.providers.nse.xbrl import parse_annual_xbrl, parse_quarterly_xbrl

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "nse" / "reliance_q1fy27_integrated.xml"


def test_parse_nse_quarterly_xbrl_fixture() -> None:
    xml_text = _FIXTURE.read_text(encoding="utf-8")
    facts = parse_quarterly_xbrl(xml_text, period_end=date(2026, 6, 30))
    assert facts is not None
    assert facts.sales is not None and facts.sales > 0
    assert facts.pat is not None and facts.pat > 0


def test_parse_nse_annual_xbrl_legacy_pl_only() -> None:
    """Legacy filings use undefined FourD context refs with P&L only (no balance sheet)."""
    xml = """
    <xbrl>
      <RevenueFromOperations contextRef="FourD">71497800000.00</RevenueFromOperations>
      <ProfitLossForPeriod contextRef="FourD">6468300000.00</ProfitLossForPeriod>
    </xbrl>
    """
    annual = parse_annual_xbrl(xml, period_end=date(2021, 3, 31))
    assert annual is not None
    assert annual.sales == Decimal("7149.78")
    assert annual.pat == Decimal("646.83")
    assert annual.total_assets is None


def test_parse_nse_annual_xbrl_minimal() -> None:
    xml = """
    <xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance">
      <xbrli:context id="FY">
        <xbrli:entity><xbrli:identifier>500325</xbrli:identifier></xbrli:entity>
        <xbrli:period>
          <xbrli:startDate>2024-04-01</xbrli:startDate>
          <xbrli:endDate>2025-03-31</xbrli:endDate>
        </xbrli:period>
      </xbrli:context>
      <Assets contextRef="FY">100000000000</Assets>
      <Equity contextRef="FY">40000000000</Equity>
      <CurrentAssets contextRef="FY">20000000000</CurrentAssets>
      <CurrentLiabilities contextRef="FY">10000000000</CurrentLiabilities>
      <ProfitLossForPeriod contextRef="FY">5000000000</ProfitLossForPeriod>
    </xbrli:xbrl>
    """
    annual = parse_annual_xbrl(xml, period_end=date(2025, 3, 31))
    assert annual is not None
    assert annual.total_assets == 10000
    assert annual.roe is not None
