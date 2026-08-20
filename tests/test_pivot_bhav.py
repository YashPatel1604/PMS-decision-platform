"""Pivot strategy bhav parse → validate → commit → reconcile loop."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from pms_platform.market_data.nse_bhav_parse import parse_bhav_file
from pms_platform.market_data.nse_bhav_store import (
    commit_bhav_run,
    stage_bhav_upload,
    upsert_portfolio_symbols,
    validate_bhav_run,
)
from pms_platform.market_data.pivot_dashboard import build_pivot_dashboard
from pms_platform.market_data.pivot_derived import floor_pivot_levels
from pms_platform.models.nse_bhav import NseBhavBar, PivotPortfolioSymbol

FIXTURES = Path(__file__).parent / "fixtures" / "pivot"


def test_floor_pivot_matches_excel_reliance_aug20() -> None:
    """Regression vs Research Daily cached values for RELIANCE on 2026-08-20."""
    levels = floor_pivot_levels(Decimal("1316.5"), Decimal("1307"), Decimal("1313.2"))
    assert abs(float(levels["pp"]) - 1312.2333333333333) < 1e-9
    assert abs(float(levels["s4"]) - 1294.2) < 1e-9
    assert abs(float(levels["r4"]) - 1332.2) < 1e-9
    assert abs(float(levels["s4_03"]) - 1290.3174) < 1e-6
    assert abs(float(levels["r1_03"]) - 1321.4190666666666) < 1e-6


def test_prune_keeps_only_20_sessions(session, tmp_path, monkeypatch) -> None:
    from datetime import timedelta

    from pms_platform.market_data.nse_bhav_store import (
        MAX_BHAV_SESSIONS,
        prune_bhav_sessions,
    )
    from pms_platform.models.nse_bhav import NseBhavBar

    monkeypatch.setattr(
        "pms_platform.market_data.nse_bhav_store.settings.upload_dir",
        tmp_path,
    )
    start = date(2026, 1, 1)
    for i in range(25):
        d = start + timedelta(days=i)
        session.add(
            NseBhavBar(
                trade_date=d,
                symbol="AAA",
                series="EQ",
                open=1,
                high=2,
                low=1,
                close=1.5,
                volume=100,
                source_key=f"{d.isoformat()}|AAA|EQ",
            )
        )
    session.commit()
    deleted = prune_bhav_sessions(session, MAX_BHAV_SESSIONS)
    session.commit()
    assert deleted >= 5
    from pms_platform.market_data.nse_bhav_store import available_trade_dates

    assert len(available_trade_dates(session)) == 20


def test_parse_fixture_single_day() -> None:
    rows = parse_bhav_file(FIXTURES / "bhav_2026-08-19.csv")
    assert len(rows) == 4
    assert {r.trade_date for r in rows} == {date(2026, 8, 19)}
    assert sum(1 for r in rows if r.series == "EQ") == 3


def test_upsert_portfolio_dedupes_and_is_idempotent(session) -> None:
    n = upsert_portfolio_symbols(
        session,
        [
            {"symbol": "UFO", "portfolio_a": False},
            {"symbol": "ufo", "portfolio_a": True, "uptrend": True},
            {"symbol": "RELIANCE", "portfolio_a": True},
        ],
    )
    assert n == 2
    session.commit()
    ufo = session.get(PivotPortfolioSymbol, "UFO")
    assert ufo is not None
    assert ufo.portfolio_a is True
    assert ufo.uptrend is True

    n2 = upsert_portfolio_symbols(
        session,
        [{"symbol": "UFO", "portfolio_a": False, "uptrend": False}],
    )
    assert n2 == 1
    session.commit()
    ufo = session.get(PivotPortfolioSymbol, "UFO")
    assert ufo is not None
    assert ufo.portfolio_a is False


def test_delete_portfolio_symbol_and_known_bhav(session, tmp_path, monkeypatch) -> None:
    from pms_platform.market_data.nse_bhav_store import (
        delete_portfolio_symbol,
        known_bhav_symbols,
        search_bhav_symbols,
        sync_bhav_file,
    )

    monkeypatch.setattr(
        "pms_platform.market_data.nse_bhav_store.settings.upload_dir",
        str(tmp_path),
    )
    sync_bhav_file(session, FIXTURES / "bhav_2026-08-19.csv")
    session.commit()
    known = known_bhav_symbols(session)
    assert "RELIANCE" in known
    assert "SHILPROCKETS" not in known
    assert search_bhav_symbols(session, "RE") == ["RELIANCE"]
    assert search_bhav_symbols(session, "R") == []

    upsert_portfolio_symbols(session, [{"symbol": "RELIANCE"}])
    session.commit()
    assert delete_portfolio_symbol(session, "reliance") is True
    session.commit()
    assert session.get(PivotPortfolioSymbol, "RELIANCE") is None
    assert delete_portfolio_symbol(session, "RELIANCE") is False


def test_open_holding_nse_symbols(session, sample_security) -> None:
    from pms_platform.market_data.pivot_dashboard import open_holding_nse_symbols
    from pms_platform.models.enums import EpisodeStatus
    from pms_platform.models.episode import InvestmentEpisode

    sample_security.current_nse_symbol = "AURIONPRO"
    session.add(
        InvestmentEpisode(
            security_id=sample_security.security_id,
            episode_number=1,
            entry_date=date(2024, 1, 1),
            status=EpisodeStatus.OPEN.value,
            initial_quantity=10,
            total_buy_quantity=10,
            final_quantity=10,
            max_quantity=10,
            number_of_buys=1,
        )
    )
    session.commit()
    assert open_holding_nse_symbols(session) == ["AURIONPRO"]


def test_bhav_validate_commit_reconcile_loop(session, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "pms_platform.market_data.nse_bhav_store.settings.upload_dir",
        tmp_path,
    )
    upsert_portfolio_symbols(
        session,
        [
            {"symbol": "RELIANCE", "portfolio_a": True, "uptrend": True},
            {"symbol": "AURIONPRO", "portfolio_a": True, "uptrend": True},
            {"symbol": "INFY", "portfolio_a": False, "uptrend": True},
        ],
    )
    session.commit()

    day1 = (FIXTURES / "bhav_2026-08-18.csv").read_bytes()
    run1 = stage_bhav_upload(session, filename="d1.csv", content=day1)
    session.flush()
    run1 = validate_bhav_run(session, run1.run_id)
    assert run1.status == "validated"
    assert run1.row_count_eq == 3
    run1 = commit_bhav_run(session, run1.run_id)
    assert run1.status == "committed", run1.error_message
    session.commit()

    day2 = (FIXTURES / "bhav_2026-08-19.csv").read_bytes()
    run2 = stage_bhav_upload(session, filename="d2.csv", content=day2)
    session.flush()
    run2 = commit_bhav_run(session, run2.run_id)
    assert run2.status == "committed", run2.reconcile_report
    assert run2.row_count_all == 4
    assert run2.row_count_eq == 3
    session.commit()

    stored = session.query(NseBhavBar).filter_by(trade_date=date(2026, 8, 19)).count()
    assert stored == 4

    dash = build_pivot_dashboard(session, as_of=date(2026, 8, 19))
    assert dash["as_of"] == "2026-08-19"
    assert len(dash["session_dates"]) == 2
    assert dash["ranks"][0]["rank"] == 1
    # INFY has higher sum turnover across window
    assert dash["ranks"][0]["symbol"] == "INFY"

    reliance = next(p for p in dash["portfolio"] if p["symbol"] == "RELIANCE")
    pivot = reliance["pivot"]
    assert pivot is not None
    assert pivot["missing"] is False
    # Same-day H/L/C on 2026-08-19: 1430 / 1400 / 1425 (Excel Daily formula).
    assert abs(pivot["pp"] - 1418.3333333333333) < 1e-9
    assert abs(pivot["r1"] - 1436.6666666666665) < 1e-9
    assert abs(pivot["s1"] - 1406.6666666666665) < 1e-9
    assert pivot["last_close"] == 1425.0

    daily_rel = next(r for r in dash["daily"] if r["symbol"] == "RELIANCE")
    assert daily_rel["portfolio_flag"] == "Y"
    assert abs(daily_rel["pivot"]["pp"] - 1418.3333333333333) < 1e-9
    assert daily_rel["vol_exp"] is not None
    assert abs(daily_rel["vol_15min"] - daily_rel["vol_exp"] / 25) < 1e-6

    gainers = dash["gainers"]
    assert gainers
    assert all(g["series"] == "EQ" for g in gainers)
