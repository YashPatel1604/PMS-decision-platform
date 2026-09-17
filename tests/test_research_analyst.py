"""Tests for research document index, search, briefs, and goals."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.config import settings
from pms_platform.documents.analyst import generate_research_ask, generate_research_brief
from pms_platform.documents.extract import extract_file, file_content_hash
from pms_platform.documents.facts import collect_security_facts
from pms_platform.documents.goals import accept_agenda_item, create_goal, list_goals, update_goal
from pms_platform.documents.indexer import index_research_corpus
from pms_platform.documents.prompts import assemble_brief_messages
from pms_platform.documents.search import SearchHit, search_research_pages
from pms_platform.documents.xai_client import XaiConfigError
from pms_platform.models import Security
from pms_platform.models.research_document import ResearchDocument


@pytest.fixture
def corpus_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "Research"
    notes = root / "Notes"
    notes.mkdir(parents=True)
    (notes / "TestCo_thesis.md").write_text(
        "TestCo promoter pledge risk and working capital stress in FY24.\n"
        "Falsifier: sustained ROCE decline below peer median.\n",
        encoding="utf-8",
    )
    (notes / "other.txt").write_text("Unrelated textile commentary.\n", encoding="utf-8")
    monkeypatch.setattr(settings, "research_dir", root)
    monkeypatch.setattr(settings, "research_corpus_globs", "**/*.md,**/*.txt")
    return root


def test_extract_and_hash_stable(corpus_root: Path) -> None:
    path = corpus_root / "Notes" / "TestCo_thesis.md"
    first = file_content_hash(path)
    second = file_content_hash(path)
    assert first == second
    result = extract_file(path)
    assert result.parse_status == "ok"
    assert result.pages[0].page_number == 1
    assert "promoter" in result.pages[0].text.lower()


def test_index_idempotent_and_search(
    session: Session, sample_security: Security, corpus_root: Path
) -> None:
    first = index_research_corpus(session, root=corpus_root)
    assert first.scanned == 2
    assert first.inserted == 2
    assert first.errors == 0

    second = index_research_corpus(session, root=corpus_root)
    assert second.unchanged == 2
    assert second.inserted == 0
    assert second.updated == 0

    docs = list(session.scalars(select(ResearchDocument)).all())
    assert len(docs) == 2
    linked = [d for d in docs if d.security_id == sample_security.security_id]
    assert linked, "path containing TestCo should link to sample security"

    hits = search_research_pages(session, "promoter pledge")
    assert hits
    assert any("promoter" in h.snippet.lower() for h in hits)


def test_outside_allowlist_not_indexed(
    session: Session, corpus_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (corpus_root / "Notes" / "secret.xlsx").write_bytes(b"not-text")
    monkeypatch.setattr(settings, "research_corpus_globs", "**/*.md")
    result = index_research_corpus(session, root=corpus_root)
    assert result.scanned == 1
    paths = [d.relative_path for d in session.scalars(select(ResearchDocument)).all()]
    assert all(p.endswith(".md") for p in paths)


def test_index_never_writes_research_files(session: Session, corpus_root: Path) -> None:
    """Indexer may only read Research; originals stay untouched on disk."""
    before = {
        path.relative_to(corpus_root).as_posix(): path.read_bytes()
        for path in corpus_root.rglob("*")
        if path.is_file()
    }
    index_research_corpus(session, root=corpus_root)
    after = {
        path.relative_to(corpus_root).as_posix(): path.read_bytes()
        for path in corpus_root.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_index_disabled_is_noop(
    session: Session, corpus_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "research_index_enabled", False)
    result = index_research_corpus(session, root=corpus_root)
    assert result.scanned == 0
    assert session.scalars(select(ResearchDocument)).all() == []


def test_goal_open_only_excludes_done(
    session: Session, sample_security: Security
) -> None:
    from pms_platform.documents.goals import create_goal, list_goals, update_goal

    open_goal = create_goal(
        session,
        security_id=sample_security.security_id,
        title="Track order book",
        status="accepted",
    )
    done_goal = create_goal(
        session,
        security_id=sample_security.security_id,
        title="Old item",
        status="accepted",
    )
    update_goal(session, done_goal.goal_id, status="done")
    open_only = list_goals(session, security_id=sample_security.security_id, open_only=True)
    assert [g.goal_id for g in open_only] == [open_goal.goal_id]


def test_ui_upload_indexes_without_research_dir(
    session: Session,
    sample_security: Security,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "research_dir", tmp_path / "no-research")
    monkeypatch.setattr(settings, "upload_dir", tmp_path / "uploads")
    from pms_platform.documents.scan import ui_corpus_dir
    from pms_platform.documents.indexer import index_uploaded_file

    dest = ui_corpus_dir(ensure=True) / "TestCo_note.md"
    dest.write_text("Promoter pledge risk note.\n", encoding="utf-8")
    action = index_uploaded_file(
        session,
        dest,
        relative_path="TestCo_note.md",
        security_id=sample_security.security_id,
    )
    assert action == "inserted"
    hits = search_research_pages(session, "promoter pledge")
    assert hits
    assert hits[0].relative_path == "TestCo_note.md"


def test_golden_fixture_corpus_searchable(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = Path(__file__).resolve().parent / "fixtures" / "research_corpus"
    monkeypatch.setattr(settings, "research_dir", root)
    monkeypatch.setattr(settings, "research_corpus_globs", "**/*.md,**/*.txt")
    result = index_research_corpus(session, root=root)
    assert result.inserted >= 1
    hits = search_research_pages(session, "promoter")
    assert hits
    assert hits[0].relative_path.endswith("TestCo_thesis.md")
    assert hits[0].page_number == 1


def test_prompt_respects_chunk_budget() -> None:
    hits = [
        SearchHit(
            page_id=i,
            document_id=1,
            relative_path=f"n{i}.md",
            page_number=1,
            title=None,
            security_id=None,
            snippet=("word " * 200) + f" token{i}",
            rank=float(10 - i),
        )
        for i in range(1, 20)
    ]
    assembled = assemble_brief_messages(
        security_label="TestCo",
        facts={"found": True, "portfolio_name": "TestCo"},
        hits=hits,
        max_chunks=3,
        max_context_tokens=500,
        snippet_chars=200,
    )
    assert len(assembled.chunk_ids) <= 3
    assert assembled.approx_tokens > 0
    payload = json.loads(assembled.messages[1]["content"])
    assert payload["injected_facts"]["portfolio_name"] == "TestCo"
    assert payload["task"] == "generate_research_brief"


def test_prompt_truncates_by_rank_then_token_budget() -> None:
    """Higher-rank pages win; later pages drop when the token cap is hit."""
    hits = [
        SearchHit(
            page_id=30,
            document_id=1,
            relative_path="low.md",
            page_number=1,
            title=None,
            security_id=None,
            snippet="low " * 80,
            rank=1.0,
        ),
        SearchHit(
            page_id=10,
            document_id=1,
            relative_path="high.md",
            page_number=1,
            title=None,
            security_id=None,
            snippet="high " * 80,
            rank=9.0,
        ),
        SearchHit(
            page_id=20,
            document_id=1,
            relative_path="mid.md",
            page_number=1,
            title=None,
            security_id=None,
            snippet="mid " * 80,
            rank=5.0,
        ),
    ]
    by_chunks = assemble_brief_messages(
        security_label="TestCo",
        facts={"found": True},
        hits=hits,
        max_chunks=2,
        max_context_tokens=50_000,
        snippet_chars=400,
    )
    assert by_chunks.chunk_ids == [10, 20]

    tight = assemble_brief_messages(
        security_label="TestCo",
        facts={"found": True},
        hits=hits,
        max_chunks=8,
        max_context_tokens=40,
        snippet_chars=400,
    )
    assert len(tight.chunk_ids) >= 1
    assert tight.chunk_ids[0] == 10
    assert len(tight.chunk_ids) < 3


def test_facts_injected_into_assembled_messages(
    session: Session, sample_security: Security
) -> None:
    facts = collect_security_facts(session, sample_security.security_id)
    assert facts["found"] is True
    assembled = assemble_brief_messages(
        security_label=str(facts["portfolio_name"]),
        facts=facts,
        hits=[],
        max_chunks=8,
        max_context_tokens=4000,
    )
    payload = json.loads(assembled.messages[1]["content"])
    assert payload["injected_facts"]["security_id"] == sample_security.security_id
    assert "open_episodes" in payload["injected_facts"]
    assert assembled.chunk_ids == []


def test_brief_without_hits_skips_llm(
    session: Session, sample_security: Security, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "xai_api_key", "should-not-be-used")
    result = generate_research_brief(session, security_id=sample_security.security_id)
    assert result.called_llm is False
    assert result.chunk_ids == []
    assert result.response["insufficient_evidence"]


def test_brief_with_mock_xai_and_cache(
    session: Session,
    sample_security: Security,
    corpus_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index_research_corpus(session, root=corpus_root)
    monkeypatch.setattr(settings, "xai_api_key", "test-key")
    hits = search_research_pages(session, "promoter")
    assert hits
    real_page_id = hits[0].page_id

    payload = {
        "id": "chat",
        "model": "grok-2-latest",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "security_query": "TestCo",
                            "thesis_map": {
                                "beliefs": ["Promoter risk matters"],
                                "must_stay_true": ["Working capital stable"],
                                "falsifiers": ["ROCE collapse"],
                            },
                            "research_agenda": [
                                {
                                    "title": "Check latest pledge disclosure",
                                    "rationale": "Notes flag promoter pledge",
                                    "priority": 1,
                                    "suggested_sources": ["filing", "ownership"],
                                }
                            ],
                            "evidence_gaps": ["Latest shareholding pattern"],
                            "monitoring_checklist": [
                                {
                                    "item": "Promoter pledge %",
                                    "cadence": "monthly",
                                    "why": "Thesis risk",
                                }
                            ],
                            "scenarios": {
                                "bull": {"summary": "Pledge declines", "citations": []},
                                "base": {"summary": "Stable", "citations": []},
                                "bear": {"summary": "Pledge rises", "citations": []},
                            },
                            "insufficient_evidence": [],
                            "citations": [
                                {
                                    "page_id": real_page_id,
                                    "document_id": hits[0].document_id,
                                    "relative_path": hits[0].relative_path,
                                    "page": hits[0].page_number,
                                    "quote_span": "promoter pledge",
                                },
                                {
                                    "page_id": 999999,
                                    "relative_path": "fake.md",
                                    "page": 1,
                                    "quote_span": "invented",
                                },
                            ],
                        }
                    ),
                }
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        assert "messages" in body
        assert all(isinstance(m.get("content"), str) for m in body["messages"])
        # No PDF / binary payloads
        joined = json.dumps(body)
        assert "%PDF" not in joined
        assert len(joined) < 200_000
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    first = generate_research_brief(
        session,
        security_id=sample_security.security_id,
        http_client=client,
    )
    assert first.called_llm is True
    assert first.response["research_agenda"][0]["title"].startswith("Check")
    assert "thesis_map" in first.response
    assert first.response["retrieved_page_ids"]
    assert all(
        c.get("page_id") in set(first.response["retrieved_page_ids"])
        for c in first.response["citations"]
        if c.get("page_id") is not None
    )
    assert all(c.get("page_id") != 999999 for c in first.response["citations"])

    second = generate_research_brief(
        session,
        security_id=sample_security.security_id,
        http_client=client,
    )
    assert second.cache_hit is True
    assert second.called_llm is False


def test_xai_retries_transient_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    from pms_platform.documents.xai_client import chat_completion

    monkeypatch.setattr(settings, "xai_api_key", "test-key")
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, text="rate limited")
        return httpx.Response(
            200,
            json={
                "model": "grok-2-latest",
                "choices": [{"message": {"content": '{"ok": true}'}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    monkeypatch.setattr("pms_platform.documents.xai_client.time.sleep", lambda *_: None)
    result = chat_completion(
        [{"role": "user", "content": "hi"}],
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert calls["n"] == 3
    assert "ok" in result.content


def test_brief_requires_key_when_hits_exist(
    session: Session,
    sample_security: Security,
    corpus_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index_research_corpus(session, root=corpus_root)
    monkeypatch.setattr(settings, "xai_api_key", "")
    with pytest.raises(XaiConfigError):
        generate_research_brief(session, security_id=sample_security.security_id)


def test_ask_empty_index(session: Session) -> None:
    result = generate_research_ask(session, question="What changed in governance?")
    assert result.called_llm is False
    assert "Insufficient evidence" in result.response["answer"]


def test_facts_and_goals(session: Session, sample_security: Security) -> None:
    facts = collect_security_facts(session, sample_security.security_id)
    assert facts["found"] is True
    assert facts["portfolio_name"] == sample_security.portfolio_name
    assert "note" in facts

    goal = create_goal(
        session,
        security_id=sample_security.security_id,
        title="Review pledge filings",
        rationale="From brief",
        priority=1,
    )
    assert goal.goal_id
    listed = list_goals(session, security_id=sample_security.security_id)
    assert len(listed) == 1
    updated = update_goal(session, goal.goal_id, status="dismissed")
    assert updated is not None and updated.status == "dismissed"
    assert list_goals(session, security_id=sample_security.security_id) == []
    assert (
        len(list_goals(session, security_id=sample_security.security_id, include_dismissed=True))
        == 1
    )


def test_goals_priority_ordering_and_accept_from_brief(
    session: Session, sample_security: Security
) -> None:
    create_goal(
        session,
        security_id=sample_security.security_id,
        title="Low priority peer check",
        priority=5,
        status="proposed",
    )
    accept_agenda_item(
        session,
        security_id=sample_security.security_id,
        title="Check latest pledge disclosure",
        rationale="From brief agenda",
        priority=1,
        source_cache_id=None,
    )
    create_goal(
        session,
        security_id=sample_security.security_id,
        title="Middle monitoring KPI",
        priority=3,
        status="accepted",
    )
    ordered = list_goals(session, security_id=sample_security.security_id)
    assert [g.title for g in ordered] == [
        "Check latest pledge disclosure",
        "Middle monitoring KPI",
        "Low priority peer check",
    ]
    assert ordered[0].status == "accepted"

    patched = update_goal(session, ordered[2].goal_id, title="Peer ROCE table", status="done")
    assert patched is not None
    assert patched.title == "Peer ROCE table"
    assert patched.status == "done"
    assert list_goals(session, security_id=sample_security.security_id)[2].status == "done"

    with pytest.raises(ValueError, match="status"):
        create_goal(
            session,
            security_id=sample_security.security_id,
            title="Bad",
            status="hold",
        )


def test_research_api_goals_and_search(
    session: Session,
    sample_security: Security,
    corpus_root: Path,
) -> None:
    """API coverage without TestClient thread/sqlite issues."""
    from pms_platform.api.routes import research as research_routes
    from pms_platform.documents.indexer import index_status

    index_research_corpus(session, root=corpus_root)
    status = index_status(session)
    assert status["document_count"] >= 1

    hits = research_routes.get_search(
        q="promoter",
        security_id=None,
        limit=20,
        as_of=None,
        session=session,
        _user=None,
    )
    assert hits

    created = research_routes.post_goal(
        research_routes.GoalCreateRequest(
            security_id=sample_security.security_id,
            title="Confirm working-capital trend",
            priority=2,
        ),
        session=session,
        user=None,
    )
    assert created.goal_id
    goals = research_routes.get_goals(
        security_id=sample_security.security_id,
        include_dismissed=False,
        session=session,
        _user=None,
    )
    assert len(goals) == 1

    patched = research_routes.patch_goal(
        created.goal_id,
        research_routes.GoalUpdateRequest(
            status="dismissed", title=None, rationale=None, priority=None
        ),
        session=session,
        _user=None,
    )
    assert patched.status == "dismissed"
    assert (
        research_routes.get_goals(
            security_id=sample_security.security_id,
            include_dismissed=False,
            session=session,
            _user=None,
        )
        == []
    )
