# Grok Research Analyst — Full Cursor Agent Plan

> **How to use this on your laptop**
>
> 1. Open `PMS-Decision-Platform.code-workspace` (so Research is indexed).
> 2. Start a Cursor Agent on a feature branch.
> 3. Paste the block in [§0 Paste-ready agent prompt](#0-paste-ready-agent-prompt) as the first message.
> 4. Keep this file open as the source of truth; do not invent a different product.
>
> **Primary goal:** improve *future* research quality by acting as an analyst (thesis maps, research agendas, evidence gaps, monitoring checklists) — not a trading bot, not a chat toy, not a number inventer.

---

## 0. Paste-ready agent prompt

Copy everything between the `BEGIN` / `END` markers into Cursor Agent on your laptop:

```text
BEGIN CURSOR AGENT PROMPT
You are implementing the Grok Research Analyst for the PMS Decision Intelligence Platform.

Read and follow, in order:
1. README.md (especially product principles: deterministic finance; LLMs may only summarize/retrieve evidence)
2. AGENTS.md (all rules; Research/ is read-only; never modify data/raw; never guess financial values)
3. PRODUCT.md (calm, rigorous, evidence-first UI)
4. docs/GROK_RESEARCH_ANALYST_PLAN.md (this plan — implement exactly; do not expand scope)

North star:
- Main goal = improve FUTURE research goals and act as an analyst assistant.
- Deliver thesis maps, ranked research agendas, evidence gaps, monitoring checklists, bull/bear/base grounded in retrieved docs + injected platform facts.
- Portfolio quantities, returns, weights, XIRR, recommendations (Hold/Review/Reduce/Exit Candidate) remain DETERMINISTIC CODE only.
- Grok must never invent numbers, place trades, or override constraints.

Architecture constraints (non-negotiable):
- Files stay on disk / OneDrive Research; do not blob PDFs into Postgres.
- Index locally (extract text → content_hash → pages + FTS). Idempotent by hash.
- Retrieve first (FTS); call xAI Grok only with top-k snippets under a hard token budget.
- Cache answers by (normalized question + chunk ids + model + prompt_version).
- Prefer storing accepted research goals over chat transcripts. Do not store full prompts by default.
- pgvector / embeddings are OUT OF SCOPE for v1 (FTS only).
- No frontend for this feature until document index + ask/brief API + tests pass (AGENTS.md #9 applied to this feature’s own backend/tests).

Implement in phases A→F as specified in docs/GROK_RESEARCH_ANALYST_PLAN.md.
Start with Phase A only unless I explicitly say to continue.
After each phase: format, lint, typecheck, tests; summarize files changed, assumptions, unresolved issues.
Create a feature branch cursor/<descriptive-name> if not already on one.
Do not modify Research/ or data/raw.
Do not silently “fix” source documents.
END CURSOR AGENT PROMPT
```

---

## 1. Product intent

### 1.1 What we are building

A **research analyst assistant** integrated into the private, local-first PMS Decision Platform:

- Helps Julesh / Samir (and Yash supporting remotely) improve **what to research next**
- Produces structured analyst outputs for a security / idea / watchlist name
- Grounds every claim in **retrieved document snippets** and/or **facts injected from deterministic platform APIs**
- Minimizes **egress to xAI** and **Postgres storage**

### 1.2 What success looks like

For a holding or watchlist name, one click / CLI call yields:

1. **Thesis map** — beliefs, what must stay true, falsifiers  
2. **Ranked research agenda** — concrete next 1–4 week work items  
3. **Evidence gap list** — missing notes, filings, ownership, peers  
4. **Monitoring checklist** — KPIs / events + suggested cadence  
5. **Bull / bear / base** — scenarios only from evidence (else “Insufficient evidence”)  
6. **Citations** — document path + page (or workbook sheet/cell ref when applicable)

Humans accept / edit / dismiss agenda items. Accepted items become durable **research goals** in Postgres (cheap, high value).

### 1.3 Explicit non-goals (never ship these)

| Forbidden | Why |
|-----------|-----|
| LLM computes returns, XIRR, weights, cash, drawdowns | README §3.1 |
| LLM invents prices, fundamentals, missing Excel cells | Never guess financial values |
| LLM auto-fires Hold/Review/Reduce/Exit | Recommendations are rule-engine + audit trail |
| LLM places trades / broker integration | Out of scope forever for v1 product |
| Uploading whole PDFs / workbooks to xAI | Egress + privacy |
| Storing full chat transcripts forever | Storage bloat |
| pgvector in v1 | README: only if FTS insufficient |
| Editing `Research/` or `data/raw` from the app/agent | Read-only lineage |
| Frontend before this feature’s backend tests pass | Parallel to AGENTS.md #9 |

### 1.4 Secondary benefits (nice, not the north star)

- Citation-backed Q&A over Research notes and filings  
- Exit / episode autopsy narratives (numbers still injected from Python)  
- Draft evidence text for a recommendation (human edits before save)  
- Weekly coverage review across holdings + watchlists  

Build these **after** the research-brief / agenda loop works.

---

## 2. Current repo context (as of plan authoring)

**Already in product:** FastAPI + Next.js app, auth, dashboard, episodes, holdings, watchlists/screener, market data, imports from OneDrive Research, client portfolio / charts / pivot strategies, Docker Compose.

**Not built yet:** `src/pms_platform/documents/` (README tree lists it; code does not exist), research search UI, LLM / xAI client, recommendation narrative assist.

**Authoritative research files:** sibling OneDrive `Research/` via `RESEARCH_DIR` (see `.env.example`). Treat as read-only. Prefer Research over `02_Final_Master` / `data/raw` duplicates when the same workbook exists.

**Stack:** Python 3.12, uv, FastAPI, SQLAlchemy, Alembic, Postgres, Next.js/pnpm UI, ruff/mypy/pytest. CLI entry: `pms-platform` → `pms_platform.cli:main`.

**Makefile gates before finish:** `make format`, `make lint`, `make typecheck`, `make test`.

---

## 3. Architecture

```text
Research/ + optional data/external filings  (files on disk; never written by this feature)
        │
        ▼
Indexer (CLI/API job)
  - walk allowlisted globs
  - sha256 content hash
  - extract text (PyMuPDF for PDF; plain/markdown/text; skip binaries we cannot parse)
  - upsert document + pages; rebuild FTS
  - skip unchanged hashes (idempotent)
        │
        ▼
Postgres (lean)
  research_documents
  research_document_pages  (+ tsvector FTS)
  research_goals           (accepted/edited agendas)
  research_answer_cache
  research_query_audit     (minimal: tokens, cache hit, security_id — not full prompts)
        │
        ▼
Retriever
  - filter by security aliases / name / ISIN when provided
  - optional as_of <= decision_date (Phase E)
  - FTS rank → top-k pages → snippet windows
        │
        ▼
Fact injector (deterministic Python — NOT Grok)
  - open holding? episode status? watchlist membership?
  - known platform metrics already computed (pass as JSON facts)
  - never ask Grok to calculate these
        │
        ▼
Prompt assembler
  - hard caps: MAX_CHUNKS, MAX_CONTEXT_TOKENS
  - system policy + structured JSON output schema
        │
        ▼
xAI Grok API (OpenAI-compatible chat)
  - only snippets + facts + question
  - no raw files
        │
        ▼
Validator
  - parse JSON
  - require citations for claims
  - mark insufficient_evidence where unsupported
        │
        ▼
Persist
  - answer cache row
  - optional research_goals upsert when user accepts
```

### 3.1 Egress minimization rules

1. Retrieve locally; send only top-k snippets.  
2. Cap context tokens (default 4000). Cap chunks (default 8).  
3. Cache by content; identical brief inputs → no API call.  
4. Never upload PDFs/xlsx.  
5. Strip client account identifiers / PII from prompts.  
6. Prefer “Generate research brief” over multi-turn chat (fewer round trips).  
7. Nightly jobs process **delta hashes only**.  
8. Skip Grok when retrieval returns zero hits — return structured “Insufficient evidence / index empty”.

### 3.2 Storage minimization rules

1. Originals on disk; DB stores path relative to `RESEARCH_DIR`, hash, mime, mtime, size.  
2. One text row per page (or logical unit); FTS `tsvector` — no embeddings in v1.  
3. Do not duplicate full document text *and* overlapping chunk copies; snippets at query time from page text + offsets.  
4. Default `RESEARCH_PROMPT_RETENTION_DAYS=0` (do not store raw prompts/completions dumps).  
5. Store short structured brief JSON + citation IDs in cache.  
6. Research goals = small rows (title, rationale, status, security_id).  
7. Corpus allowlist — index holdings + watchlist-related trees first, not entire historical dump on day one.

---

## 4. Configuration

Add to `.env.example` (and document in this file; do not commit real keys):

```bash
# --- Research analyst / Grok (optional) ---
XAI_API_KEY=
XAI_API_BASE_URL=https://api.x.ai/v1
XAI_MODEL=grok-2-latest
# Pin a dated model id in production when available.

RESEARCH_INDEX_ENABLED=1
# Comma-separated globs relative to RESEARCH_DIR. Tighten before first full index.
RESEARCH_CORPUS_GLOBS=**/*.pdf,**/*.md,**/*.txt
# Optional exclude globs
RESEARCH_CORPUS_EXCLUDE_GLOBS=**/~*,**/.tmp/**

RESEARCH_RAG_MAX_CHUNKS=8
RESEARCH_RAG_MAX_CONTEXT_TOKENS=4000
RESEARCH_RAG_SNIPPET_CHARS=1200
RESEARCH_ANSWER_CACHE_TTL_DAYS=30
RESEARCH_PROMPT_RETENTION_DAYS=0
RESEARCH_ANALYST_PROMPT_VERSION=v1
```

Wire via existing `pms_platform.config` settings pattern (pydantic-settings). Feature must no-op cleanly when `XAI_API_KEY` is empty (index + FTS still work).

---

## 5. Data model (Phase A migration)

Suggested tables (names may match repo conventions; use Alembic):

### `research_documents`
- `id` UUID/PK  
- `relative_path` TEXT NOT NULL (unique)  
- `content_hash` CHAR(64) NOT NULL  
- `source_root` TEXT NOT NULL  -- e.g. `research`  
- `mime_type` TEXT NULL  
- `byte_size` BIGINT NULL  
- `mtime_utc` TIMESTAMPTZ NULL  
- `title` TEXT NULL  
- `indexed_at` TIMESTAMPTZ NOT NULL  
- `parse_status` TEXT NOT NULL  -- ok | skipped | error  
- `parse_error` TEXT NULL  
- `security_id` FK NULL  -- optional link when resolvable  
- lineage: preserve path + hash (do not “correct” files)

### `research_document_pages`
- `id` PK  
- `document_id` FK CASCADE  
- `page_number` INT NOT NULL  -- 1-based; use 1 for single-unit text files  
- `text` TEXT NOT NULL  
- `tsv` TSVECTOR  -- generated/maintained for FTS  
- UNIQUE(document_id, page_number)

Indexes: GIN(`tsv`), optional btree on `document_id`.

### `research_goals`
- `id` PK  
- `security_id` FK NOT NULL  
- `title` TEXT NOT NULL  
- `rationale` TEXT NULL  
- `priority` INT NOT NULL DEFAULT 0  
- `status` TEXT NOT NULL  -- proposed | accepted | done | dismissed  
- `source_brief_id` NULL FK to cache/audit  
- `created_at`, `updated_at`  
- `created_by_user` TEXT NULL  

### `research_answer_cache`
- `id` PK  
- `cache_key` CHAR(64) UNIQUE NOT NULL  
- `security_id` FK NULL  
- `request_kind` TEXT NOT NULL  -- brief | ask | coverage  
- `response_json` JSONB NOT NULL  
- `citation_page_ids` BIGINT[] or JSONB  
- `model` TEXT NOT NULL  
- `prompt_version` TEXT NOT NULL  
- `token_in` INT NULL  
- `token_out` INT NULL  
- `created_at`  
- `expires_at`  

### `research_query_audit`
- `id` PK  
- `created_at`  
- `request_kind`  
- `security_id` NULL  
- `cache_hit` BOOL  
- `token_in`, `token_out`  
- `latency_ms`  
- `error` TEXT NULL  
- **Do not** store full prompt/response unless `RESEARCH_PROMPT_RETENTION_DAYS > 0` (then schedule purge).

---

## 6. Structured output schema (Grok must return JSON)

```json
{
  "security_query": "string",
  "thesis_map": {
    "beliefs": ["..."],
    "must_stay_true": ["..."],
    "falsifiers": ["..."]
  },
  "research_agenda": [
    {
      "title": "string",
      "rationale": "string",
      "priority": 1,
      "suggested_sources": ["filing", "notes", "peer", "ownership"]
    }
  ],
  "evidence_gaps": ["..."],
  "monitoring_checklist": [
    {"item": "string", "cadence": "weekly|monthly|event", "why": "string"}
  ],
  "scenarios": {
    "bull": {"summary": "string", "citations": ["doc:page"]},
    "base": {"summary": "string", "citations": ["doc:page"]},
    "bear": {"summary": "string", "citations": ["doc:page"]}
  },
  "insufficient_evidence": ["..."],
  "citations": [
    {"document_id": "...", "relative_path": "...", "page": 1, "quote_span": "short"}
  ]
}
```

System prompt rules (encode in code, version as `RESEARCH_ANALYST_PROMPT_VERSION`):

- Answer ONLY from provided snippets + injected facts.  
- If unsupported, put the topic under `insufficient_evidence` — do not invent.  
- Never output numeric portfolio returns/weights unless they appear in `injected_facts`.  
- Never recommend trade sizes or broker actions.  
- Prefer specific, falsifiable research tasks over vague “dig deeper”.  
- Every scenario claim needs citations when docs exist.

---

## 7. Implementation phases

Implement **one phase per PR/agent session** unless the user says otherwise. Check boxes in a follow-up issue/PR description as you go.

### Phase A — Document index + FTS (no Grok)

**Build**
- Package `src/pms_platform/documents/`:
  - `scan.py` — walk allowlisted globs under `RESEARCH_DIR`
  - `extract.py` — PDF via PyMuPDF (`pymupdf`); md/txt as utf-8; record skip/error otherwise
  - `indexer.py` — hash, upsert, delete missing paths (optional soft-orphan flag)
  - `search.py` — FTS query → ranked pages + snippets
- Alembic migration for tables above (goals/cache can be created empty now or in Phase C)
- CLI:
  - `pms-platform research-index`
  - `pms-platform research-search --query "..."`  
- API (auth required like other routes):
  - `POST /research/index` (kick job; sync OK for v1 if corpus small)
  - `GET /research/search?q=&security_id=&limit=`
  - `GET /research/documents` status counts

**Dependencies:** add `pymupdf` to `pyproject.toml` via uv.

**Tests**
- Idempotent re-index (same hash → no page churn)
- Search finds known fixture text
- Path outside allowlist not indexed
- Never writes into Research/

**Exit criteria:** Keyword search returns path + page from a test fixture corpus.

---

### Phase B — Fact injector + brief prompt assembly (still mockable without live xAI)

**Build**
- `documents/facts.py` — gather deterministic facts for `security_id` from existing services (holding open?, watchlists, any already-computed metrics available without new finance formulas)
- `documents/prompts.py` — build messages under token budget (approximate with chars/4 or tiktoken-lite if already acceptable; keep simple deterministic truncation by rank order)
- Unit tests with canned pages asserting chunk cap and truncation order

**Exit criteria:** Given fixtures, assembler produces messages with ≤ MAX_CHUNKS and includes injected facts JSON.

---

### Phase C — xAI Grok client + research brief API

**Build**
- `documents/xai_client.py` — httpx client, timeouts, retries on 429/5xx, token usage parse
- `documents/analyst.py` — `generate_research_brief(security_id|name, ...)` orchestration
- Cache key = sha256 of normalized inputs
- API:
  - `POST /research/brief` `{ "security_id": "...", "extra_question": null }`
  - `POST /research/ask` `{ "question": "...", "security_id": optional }` (secondary)
- CLI: `pms-platform research-brief --security-id ...`
- If `XAI_API_KEY` missing → HTTP 503 with clear message; index/search still work

**Tests**
- httpx mock: assert no PDF bytes in request; body size under budget
- cache hit skips HTTP
- empty retrieval → insufficient_evidence structure without calling API (or one call with empty context that model must refuse — prefer **no call**)

**Exit criteria:** Brief JSON validates against schema; citations reference real page ids from retrieval.

---

### Phase D — Research goals persistence

**Build**
- API:
  - `GET /research/goals?security_id=`
  - `POST /research/goals` (accept from brief item)
  - `PATCH /research/goals/{id}` status/title
- From brief response, UI/CLI can accept agenda rows → `status=accepted`
- Audit minimal fields on each brief generation

**Tests:** CRUD, dismiss, priority ordering.

**Exit criteria:** Accepted goals survive restart; dismissed not shown by default.

---

### Phase E — UI (only after A–D tests green)

**Build (keep PRODUCT.md: calm, no trading-terminal clutter)**
- New page `/research` or panel on holdings/watchlist/episode:
  - Search box (FTS results)
  - “Generate research brief” for selected security
  - Render thesis / agenda / gaps / monitoring / scenarios
  - Citations as links/labels (path + page)
  - Accept / dismiss agenda → goals list
- Reuse existing auth-gate, app-shell nav, TanStack Query patterns
- Avoid card spam in hero; this is a tool page — one job per section

**Exit criteria:** Dad can open a watchlist name, generate brief, accept 2 goals, refresh, still see them.

---

### Phase F — Forward-looking loops (analyst depth)

**Build**
- **Weekly coverage job:** for each open holding + default watchlist members, if no accepted open goals or stale brief → queue brief (respect rate limits / budget)
- **Delta briefs:** when `content_hash` changes for docs linked to a security → “what changed for research agenda?” prompt variant using only new pages + prior accepted goals
- **Point-in-time mode (optional):** `as_of` filter for historical decision lab — exclude pages/docs with mtime/as_of after date when metadata exists; if as_of unknown, exclude from PIT mode rather than guessing

**Exit criteria:** Delta path does not re-send unchanged corpus; coverage job is opt-in CLI.

---

## 8. API sketch

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/research/index` | Run index (idempotent) |
| GET | `/research/status` | Doc counts, last indexed_at, parse errors |
| GET | `/research/search` | FTS hits |
| POST | `/research/brief` | Analyst brief JSON |
| POST | `/research/ask` | Freeform Q&A with citations (secondary) |
| GET/POST/PATCH | `/research/goals` | Research goal CRUD |

Register router in `api/main.py` with auth middleware consistent with other routes.

---

## 9. Security, privacy, ops

- Auth required; invite-only users only.  
- API key only in env / Docker secret; never log the key.  
- Assume snippets may leave the machine to xAI — document this in UI help text once.  
- If privacy policy becomes “no cloud LLM”, keep Phases A–B as local search; swap client for local model later behind same interface.  
- Rate-limit brief generation per user (simple in-memory or DB cooldown) to protect cost.  
- Log token_in/out daily for cost awareness.

---

## 10. Testing strategy

- Unit: hash, extract fixtures, FTS, prompt budget, cache key stability, JSON schema validation.  
- API tests with TestClient + mocked xAI.  
- Golden fixture PDF/md under `tests/fixtures/research_corpus/` (repo-owned; not OneDrive).  
- Never require live `XAI_API_KEY` in CI.  
- Regression: indexing must not touch holdings/returns tables.

---

## 11. Definition of done (whole feature)

- [ ] Phase A index + FTS shipped with tests  
- [ ] Phase B fact injector + prompt budget  
- [ ] Phase C Grok brief + cache + no-key graceful failure  
- [ ] Phase D research goals CRUD  
- [ ] Phase E UI brief + accept goals  
- [ ] Phase F optional delta/coverage CLI  
- [ ] `.env.example` updated  
- [ ] README short subsection under Document intelligence pointing to this doc  
- [ ] `make format && make lint && make typecheck && make test` green  
- [ ] Summary of files changed, assumptions, unresolved issues  

---

## 12. Suggested agent session order (laptop)

1. Paste §0 prompt → implement **Phase A** only → PR.  
2. New session: Phase B → PR.  
3. New session: Phase C (needs your `XAI_API_KEY` locally for manual smoke; CI stays mocked) → PR.  
4. Phase D → PR.  
5. Phase E UI → PR.  
6. Phase F only if A–E used in real life for a week.

Manual smoke on laptop (after C):

```bash
# ensure RESEARCH_DIR points at OneDrive Research
uv sync
uv run pms-platform research-index
uv run pms-platform research-search --query "promoter"
uv run pms-platform research-brief --security-id <uuid>
```

---

## 13. Prompt for later sessions (continue work)

```text
Continue Grok Research Analyst per docs/GROK_RESEARCH_ANALYST_PLAN.md.
Previous phase is done on this branch/main. Implement the NEXT unchecked phase only.
Do not expand into embeddings/pgvector or trade execution.
Follow AGENTS.md + README principles. Run format/lint/typecheck/tests before finishing.
```

---

## 14. Ambiguities — stop and ask the user

Flag and stop if:

- Indexing would alter historical holdings/returns (it must not — if a design couples them, stop).  
- Corpus allowlist would ingest client-identifying account statements you did not intend to send snippets from.  
- xAI model id / pricing / ToS unclear for production pin.  
- PIT `as_of` for documents cannot be determined without guessing publication dates.  
- Any request to let Grok compute official performance numbers.

---

## 15. One-line summary

**Index Research locally with FTS → inject platform facts → ask Grok for a citation-backed research brief and agenda → store accepted goals — never let the model touch portfolio math or execution.**
