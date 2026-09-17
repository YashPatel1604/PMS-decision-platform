"""Investment theses, portfolio events, and morning brief."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from pms_platform.intelligence.brief import build_morning_brief
from pms_platform.intelligence.conflicts import create_conflict_flag
from pms_platform.intelligence.events import _rule_materiality, upsert_event
from pms_platform.intelligence.theses import create_thesis, list_theses, revise_thesis
from pms_platform.models import Security


def test_rule_materiality_keywords() -> None:
    assert _rule_materiality("Promoter share pledge filed")[0] == "WATCH"
    assert _rule_materiality("CEO resignation announced")[0] == "REVIEW"
    assert _rule_materiality("Insider disposal disclosed")[0] == "INFORMATIONAL"


def test_thesis_versioning_and_brief(
    session: Session, sample_security: Security
) -> None:
    first = create_thesis(
        session,
        security_id=sample_security.security_id,
        thesis_summary="Quality compounder",
        margin_assumption="Stable 18% EBITDA",
        created_by="test",
    )
    assert first.version == 1
    assert first.status == "active"

    second = revise_thesis(
        session,
        first.thesis_id,
        thesis_summary="Quality compounder with WC risk",
        created_by="test",
    )
    assert second.version == 2
    assert second.status == "active"
    assert second.margin_assumption == "Stable 18% EBITDA"

    actives = list_theses(session, security_id=sample_security.security_id, active_only=True)
    assert len(actives) == 1
    assert actives[0].thesis_id == second.thesis_id

    session.refresh(first)
    assert first.status == "superseded"

    upsert_event(
        session,
        dedupe_key="test-pledge-1",
        event_type="share_pledge",
        summary="Promoter pledged 4% stake",
        materiality="WATCH",
        materiality_reason="Rule: share pledge",
        source="test",
        security_id=sample_security.security_id,
        company="TestCo",
        event_date=date.today(),
        universe="holding",
    )
    create_conflict_flag(
        session,
        thesis_id=second.thesis_id,
        security_id=sample_security.security_id,
        assumption_affected="margin_assumption",
        what_changed="Pledge may signal cash stress",
        severity="medium",
        evidence="test-pledge-1",
    )

    brief = build_morning_brief(session, lookback_days=7)
    assert brief["counts"]["needs_attention"] >= 1
    assert any(e["summary"].startswith("Promoter pledged") for e in brief["needs_attention"])
    assert all(e["universe"] in ("holding", "watchlist") for e in brief["needs_attention"])
    assert any(p["code"] == "thesis_conflict" for p in brief["data_problems"])


def test_needs_attention_excludes_other_universe(
    session: Session, sample_security: Security
) -> None:
    from datetime import date

    from pms_platform.intelligence.brief import build_morning_brief
    from pms_platform.intelligence.events import upsert_event

    upsert_event(
        session,
        dedupe_key="other-urgent",
        event_type="test",
        summary="Unrelated promoter resignation",
        materiality="REVIEW",
        materiality_reason="test",
        source="test",
        event_date=date.today(),
        universe="other",
    )
    brief = build_morning_brief(session, lookback_days=7)
    assert brief["needs_attention"] == []


def test_intelligence_api_brief(session: Session, sample_security: Security) -> None:
    from pms_platform.api.routes import intelligence as intelligence_routes

    upsert_event(
        session,
        dedupe_key="api-event-1",
        event_type="insider_transaction",
        summary="Insider acquisition disclosed",
        materiality="INFORMATIONAL",
        materiality_reason="Rule: insider",
        source="test",
        security_id=sample_security.security_id,
        event_date=date.today(),
        universe="holding",
    )
    payload = intelligence_routes.get_brief(lookback_days=7, session=session, _user=None)
    assert "needs_attention" in payload
    assert payload["as_of"] == date.today().isoformat()

    theses = intelligence_routes.post_thesis(
        intelligence_routes.ThesisBody(
            security_id=sample_security.security_id,
            thesis_summary="API thesis",
        ),
        session=session,
        user=None,
    )
    assert theses["version"] == 1
    assert theses["thesis_summary"] == "API thesis"
