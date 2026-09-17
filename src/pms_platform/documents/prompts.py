"""Prompt assembly with hard chunk/token budgets (egress control)."""

from __future__ import annotations

import json
from dataclasses import dataclass

from pms_platform.config import settings
from pms_platform.documents.search import SearchHit

ANALYST_SYSTEM_PROMPT = """You are a research analyst assistant for a private Indian PMS.
Your job is to improve FUTURE research quality: thesis maps, ranked research agendas,
evidence gaps, monitoring checklists, and bull/base/bear scenarios.

Hard rules:
- Use ONLY the provided document snippets and injected_facts.
- Never invent prices, fundamentals, returns, weights, XIRR, or missing cells.
- Never recommend trade sizes, broker actions, or automatic Hold/Review/Reduce/Exit.
- If evidence is missing, list it under insufficient_evidence — do not guess.
- Every scenario claim must cite snippets when docs exist (path + page).
- Prefer specific, falsifiable research tasks over vague advice.
- Respond with a single JSON object matching the required schema. No markdown fences.
"""

BRIEF_SCHEMA_HINT = {
    "security_query": "string",
    "thesis_map": {
        "beliefs": ["..."],
        "must_stay_true": ["..."],
        "falsifiers": ["..."],
    },
    "research_agenda": [
        {
            "title": "string",
            "rationale": "string",
            "priority": 1,
            "suggested_sources": ["filing", "notes", "peer", "ownership"],
        }
    ],
    "evidence_gaps": ["..."],
    "monitoring_checklist": [
        {"item": "string", "cadence": "weekly|monthly|event", "why": "string"}
    ],
    "scenarios": {
        "bull": {"summary": "string", "citations": ["path:page"]},
        "base": {"summary": "string", "citations": ["path:page"]},
        "bear": {"summary": "string", "citations": ["path:page"]},
    },
    "insufficient_evidence": ["..."],
    "citations": [
        {
            "document_id": 0,
            "relative_path": "...",
            "page": 1,
            "quote_span": "short",
        }
    ],
}


@dataclass(frozen=True)
class AssembledPrompt:
    messages: list[dict[str, str]]
    chunk_ids: list[int]
    approx_tokens: int


def _approx_tokens(text: str) -> int:
    # Deterministic coarse estimate; avoids extra deps.
    return max(1, len(text) // 4)


def assemble_brief_messages(
    *,
    security_label: str,
    facts: dict[str, object],
    hits: list[SearchHit],
    extra_question: str | None = None,
    max_chunks: int | None = None,
    max_context_tokens: int | None = None,
    snippet_chars: int | None = None,
) -> AssembledPrompt:
    """Build chat messages under hard egress budgets."""
    max_chunks = max_chunks if max_chunks is not None else settings.research_rag_max_chunks
    max_context_tokens = (
        max_context_tokens
        if max_context_tokens is not None
        else settings.research_rag_max_context_tokens
    )
    snippet_chars = (
        snippet_chars if snippet_chars is not None else settings.research_rag_snippet_chars
    )

    selected: list[SearchHit] = []
    used_tokens = 0
    for hit in hits:
        if len(selected) >= max_chunks:
            break
        snippet = hit.snippet if len(hit.snippet) <= snippet_chars else hit.snippet[:snippet_chars]
        block = (
            f"[{len(selected) + 1}] path={hit.relative_path} page={hit.page_number} "
            f"page_id={hit.page_id} doc_id={hit.document_id}\n{snippet}"
        )
        cost = _approx_tokens(block)
        if selected and used_tokens + cost > max_context_tokens:
            break
        if not selected and cost > max_context_tokens:
            # Always allow one truncated chunk so empty-context path is intentional.
            block = block[: max_context_tokens * 4]
            cost = _approx_tokens(block)
        selected.append(
            SearchHit(
                page_id=hit.page_id,
                document_id=hit.document_id,
                relative_path=hit.relative_path,
                page_number=hit.page_number,
                title=hit.title,
                security_id=hit.security_id,
                snippet=snippet if len(snippet) <= snippet_chars else snippet[:snippet_chars],
                rank=hit.rank,
            )
        )
        used_tokens += cost

    context_blocks = []
    for i, hit in enumerate(selected, start=1):
        context_blocks.append(
            f"[{i}] path={hit.relative_path} page={hit.page_number} "
            f"page_id={hit.page_id} doc_id={hit.document_id}\n{hit.snippet}"
        )
    context_text = (
        "\n\n".join(context_blocks) if context_blocks else "(no document snippets retrieved)"
    )

    user_payload = {
        "task": "generate_research_brief",
        "security_query": security_label,
        "extra_question": extra_question,
        "injected_facts": facts,
        "document_snippets": context_text,
        "required_json_schema": BRIEF_SCHEMA_HINT,
        "prompt_version": settings.research_analyst_prompt_version,
    }
    user_content = json.dumps(user_payload, ensure_ascii=False, default=str)
    messages = [
        {"role": "system", "content": ANALYST_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
    return AssembledPrompt(
        messages=messages,
        chunk_ids=[hit.page_id for hit in selected],
        approx_tokens=_approx_tokens(ANALYST_SYSTEM_PROMPT) + _approx_tokens(user_content),
    )


def assemble_ask_messages(
    *,
    question: str,
    facts: dict[str, object] | None,
    hits: list[SearchHit],
    max_chunks: int | None = None,
    max_context_tokens: int | None = None,
    snippet_chars: int | None = None,
) -> AssembledPrompt:
    """Secondary freeform Q&A with citations — still budget-capped."""
    brief = assemble_brief_messages(
        security_label=str((facts or {}).get("portfolio_name") or "unknown"),
        facts=facts or {"found": False},
        hits=hits,
        extra_question=question,
        max_chunks=max_chunks,
        max_context_tokens=max_context_tokens,
        snippet_chars=snippet_chars,
    )
    # Re-tag task for ask mode without rebuilding budgets.
    payload = json.loads(brief.messages[1]["content"])
    payload["task"] = "research_ask"
    payload["question"] = question
    messages = [
        brief.messages[0],
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
    ]
    return AssembledPrompt(
        messages=messages,
        chunk_ids=brief.chunk_ids,
        approx_tokens=_approx_tokens(messages[0]["content"])
        + _approx_tokens(messages[1]["content"]),
    )
