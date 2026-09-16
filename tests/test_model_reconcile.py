"""Close OPEN episodes missing from Client Portfolio Model; open Model-only names."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from helpers import add_transaction
from pms_platform.episodes.builder import build_episodes
from pms_platform.episodes.model_reconcile import (
    ensure_open_episodes_for_client_model,
    reconcile_open_episodes_to_client_model,
)
from pms_platform.market_data.client_portfolio_parse import (
    ClientPortfolioBook,
    ClientPortfolioPosition,
)
from pms_platform.models import InvestmentEpisode, Security
from pms_platform.models.enums import EpisodeStatus, EventType
from pms_platform.models.nse_bhav import NseBhavBar
from sqlalchemy import select


def test_reconcile_closes_open_episode_absent_from_model(
    session, import_batch, sample_security, monkeypatch
) -> None:
    sample_security.current_nse_symbol = "WELENT"
    add_transaction(
        session,
        import_batch,
        sample_security.security_id,
        date(2023, 8, 4),
        EventType.BUY,
        100,
        1,
        Decimal("50"),
    )
    session.flush()
    build_episodes(session)
    session.flush()

    ep = session.scalars(select(InvestmentEpisode)).one()
    assert ep.status == EpisodeStatus.OPEN.value
    assert ep.final_quantity == 100

    session.add(
        NseBhavBar(
            trade_date=date(2026, 8, 20),
            symbol="WELENT",
            series="EQ",
            isin=None,
            instrument_name="Wel",
            open=Decimal("500"),
            high=Decimal("520"),
            low=Decimal("490"),
            close=Decimal("510"),
            prev_close=Decimal("500"),
            volume=1,
            turnover=None,
            source_key="test|WELENT|EQ|2026-08-20",
        )
    )
    session.flush()

    fake_book = ClientPortfolioBook(
        path=Path("fixture.xlsx"),
        mtime=1.0,
        model=[
            ClientPortfolioPosition(
                symbol=sym,
                qty=Decimal(1),
                excel_price=Decimal(100),
                excel_value=Decimal(100),
                excel_percent=Decimal(100),
            )
            for sym in ("RELIANCE", "INFY", "TCS")
        ],
        stocks_qty={},
        excel_total_value=Decimal(300),
    )
    monkeypatch.setattr(
        "pms_platform.episodes.model_reconcile.resolve_client_portfolio_book",
        lambda session: fake_book,
    )

    closed = reconcile_open_episodes_to_client_model(session)
    session.commit()
    assert len(closed) == 1
    assert closed[0].portfolio_name == "TestCo"
    assert closed[0].quantity_closed == 100
    assert closed[0].exit_price == Decimal("510")

    session.refresh(ep)
    assert ep.status == EpisodeStatus.CLOSED.value
    assert ep.final_quantity == 0
    assert ep.exit_date == date(2026, 8, 20)


def _synthetic_sec(session, symbol: str, batch_id: int) -> Security:
    sid = f"MDL{symbol}"[:16]
    sec = session.get(Security, sid)
    if sec is not None:
        return sec
    sec = Security(
        security_id=sid,
        portfolio_name=symbol,
        canonical_name=symbol,
        current_nse_symbol=symbol,
        status="ACTIVE",
        verification_status="CLIENT_MODEL",
        import_batch_id=batch_id,
    )
    session.add(sec)
    session.flush()
    return sec


def test_ensure_opens_model_symbol_missing_from_holdings(session, import_batch, monkeypatch) -> None:
    session.add(
        NseBhavBar(
            trade_date=date(2026, 9, 15),
            symbol="JYOTICNC",
            series="EQ",
            isin=None,
            instrument_name="Jyoti",
            open=Decimal("900"),
            high=Decimal("1000"),
            low=Decimal("890"),
            close=Decimal("961.45"),
            prev_close=Decimal("950"),
            volume=1,
            turnover=None,
            source_key="test|JYOTICNC|EQ|2026-09-15",
        )
    )
    session.flush()

    fake_book = ClientPortfolioBook(
        path=Path("fixture.xlsx"),
        mtime=1.0,
        model=[
            ClientPortfolioPosition(
                symbol=sym,
                qty=Decimal(qty),
                excel_price=Decimal(100),
                excel_value=Decimal(100),
                excel_percent=Decimal(10),
            )
            for sym, qty in (("RELIANCE", 1), ("INFY", 1), ("TCS", 1), ("JYOTICNC", 1995))
        ],
        stocks_qty={},
        excel_total_value=Decimal(400),
    )
    monkeypatch.setattr(
        "pms_platform.episodes.model_reconcile.resolve_client_portfolio_book",
        lambda session: fake_book,
    )
    monkeypatch.setattr(
        "pms_platform.episodes.model_reconcile._ensure_security_for_model_symbol",
        lambda session, symbol: _synthetic_sec(session, symbol, import_batch.import_batch_id),
    )

    opened = ensure_open_episodes_for_client_model(session, as_of=date(2026, 9, 15))
    session.commit()
    by_sym = {row.symbol: row for row in opened}
    assert "JYOTICNC" in by_sym
    assert by_sym["JYOTICNC"].quantity == 1995
    ep = session.get(InvestmentEpisode, by_sym["JYOTICNC"].episode_id)
    assert ep is not None
    assert ep.status == EpisodeStatus.OPEN.value
    assert ep.final_quantity == 1995
