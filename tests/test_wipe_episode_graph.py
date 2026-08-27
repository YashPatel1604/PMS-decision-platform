"""Episode wipe must clear cash-flow / decision FKs before episodes."""

from datetime import date
from decimal import Decimal

from helpers import add_transaction
from pms_platform.episodes.builder import build_episodes, wipe_episode_graph
from pms_platform.models import EpisodeCashFlowRecord, InvestmentEpisode
from pms_platform.models.enums import EventType
from sqlalchemy import func, select


def test_wipe_episode_graph_clears_cash_flows(
    session, import_batch, sample_security
) -> None:
    add_transaction(
        session,
        import_batch,
        sample_security.security_id,
        date(2020, 1, 2),
        EventType.BUY,
        10,
        1,
        Decimal("100"),
    )
    session.flush()
    episodes, _ = build_episodes(session)
    session.flush()
    assert len(episodes) == 1
    session.add(
        EpisodeCashFlowRecord(
            episode_id=episodes[0].episode_id,
            flow_date=date(2020, 1, 2),
            amount=Decimal("-1000"),
            flow_type="BUY",
            source="test",
            source_reference=None,
            calculation_version="test",
        )
    )
    session.flush()
    assert session.scalar(select(func.count()).select_from(EpisodeCashFlowRecord)) == 1

    wipe_episode_graph(session)
    session.flush()
    assert session.scalar(select(func.count()).select_from(EpisodeCashFlowRecord)) == 0
    assert session.scalar(select(func.count()).select_from(InvestmentEpisode)) == 0
