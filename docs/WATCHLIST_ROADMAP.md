# Watchlist + Fundamentals Screener — Issue Checklist

Track implementation progress. Check boxes as each item ships to `main`.

**Principles:** deterministic metrics, idempotent refresh, import audit trails, fail visibly.

---

## Phase 1 — Watchlist foundation

- [x] **P1.1** Alembic migration: `watchlists`, `watchlist_members`
- [x] **P1.2** ORM models + relationships
- [x] **P1.3** Service layer: CRUD, duplicate guards, default watchlist rules
- [x] **P1.4** API: `GET/POST/PATCH/DELETE /watchlists`
- [x] **P1.5** API: `GET/POST/DELETE /watchlists/{id}/members`
- [x] **P1.6** API: `GET /watchlists/search?q=` (security master typeahead)
- [x] **P1.7** UI: `/watchlists` — list picker, create/rename/delete
- [x] **P1.8** UI: add/remove members, empty states, confirm delete
- [x] **P1.9** Nav link in app shell
- [x] **P1.10** Unit tests: CRUD, duplicate 409, cascade delete, default rules
- [ ] **P1.11** Optional CLI seed from Research Excel (`seed-watchlist`)

**Exit criteria:** Dad creates 3 watchlists, adds/removes stocks, survives Docker restart.

---

## Phase 2 — Symbol resolution

- [x] **P2.1** Resolution pipeline: master → BSE universe → Yahoo search
- [x] **P2.2** `resolution_status` + stale re-resolve (7 days)
- [x] **P2.3** Resolution log table for failures
- [x] **P2.4** UI: ⚠ unresolved badge + manual symbol fix
- [x] **P2.5** Tests: Heritage, MOSL, unknown small cap

**Exit criteria:** ≥95% of 200 names resolve automatically.

---

## Phase 3 — Fundamentals data layer

- [x] **P3.1** Versioned CSV contract `quarterly_fundamentals.csv`
- [x] **P3.2** Tables: `company_fundamentals_quarterly`, `fundamental_snapshots`
- [x] **P3.3** Metric catalog config (extensible column definitions)
- [x] **P3.4** `FundamentalsProvider` interface
- [x] **P3.5** Manual CSV + Screener export provider (MVP)
- [x] **P3.6** Yahoo fundamentals fallback provider
- [x] **P3.7** Compute: sales YoY/QoQ, OPM/NPM Δ pp, PAT YoY
- [x] **P3.8** `computation_version` on snapshots
- [x] **P3.9** Import batch + checksum audit
- [x] **P3.10** Tests: idempotent ingest, null-safe math, golden fixtures

**Exit criteria:** 50+ companies, 4+ quarters, re-sync is idempotent.

---

## Phase 4 — Screener UI

- [x] **P4.1** API: `GET /watchlists/{id}/screen?columns=&sort=`
- [x] **P4.2** Column picker (grouped: Growth / Margins / Valuation)
- [x] **P4.3** Sortable headers (asc/desc, nulls last)
- [x] **P4.4** Saved views in localStorage
- [x] **P4.5** Export current view to CSV
- [x] **P4.6** Stale-data badges (`retrieved_at` > 90 days)

**Exit criteria:** Sort 200 rows by sales growth; column picker works.

---

## Phase 5 — Promoter & insider alerts

- [x] **P5.1** Table: `watchlist_alerts` with dedupe key
- [x] **P5.2** Poller: SAST + insider filtered to watchlist BSE codes
- [x] **P5.3** API: `GET /watchlists/{id}/alerts`, acknowledge
- [x] **P5.4** UI: alert strip + nav badge
- [x] **P5.5** Tests: no duplicate alerts, watchlist scoping

**Exit criteria:** Heritage SAST appears only when on watchlist.

---

## Phase 6 — Refresh automation

- [x] **P6.1** API: `POST /watchlists/{id}/refresh` (resolve + fundamentals + alerts)
- [x] **P6.2** Mutex: reject concurrent refresh (409)
- [x] **P6.3** Structured refresh result (ok/failed counts)
- [x] **P6.4** CLI: `pms-platform sync-watchlists`
- [x] **P6.5** Windows script: `scripts/windows/refresh-watchlists.ps1`
- [x] **P6.6** Docs: cadence in `WINDOWS_DAD_SETUP.md` (daily alerts, weekly fundamentals)

**Exit criteria:** One-button refresh; scheduled task documented.

---

## Phase 7 — Long-term hardening

- [x] **P7.1** Provider setting: `FUNDAMENTALS_PROVIDER=screener|yahoo|manual`
- [x] **P7.2** Watchlist export/import JSON/CSV
- [x] **P7.3** `/watchlists/health` data-quality dashboard
- [x] **P7.4** Migration test: fresh install + upgrade path
- [x] **P7.5** Golden regression tests (Heritage/MOSL metrics)
- [x] **P7.6** BSE fundamentals provider (`xbrl` — TabResults_PAR API; Phase C)

---

## Phase C — BSE fundamentals (xbrl provider)

- [x] **PC.1** BSE `TabResults_PAR` fetch + parse (sales, PAT, OPM, NPM)
- [x] **PC.2** `XbrlFundamentalsProvider` upserts by `BSE_CODE`
- [x] **PC.3** CLI + `FUNDAMENTALS_PROVIDER=xbrl` sync path
- [x] **PC.4** Tests with mocked BSE responses
- [x] **PC.5** XBRL historical backfill (`GetCorXbrlDetails_ng`, Flag=22) for YoY/QoQ depth


| Risk | Mitigation |
|------|------------|
| Wrong stock matched | Resolution confidence + manual override |
| Stale fundamentals | `retrieved_at` badge + row styling |
| BSE timeout | Retry 3×, cache last good, error banner |
| Duplicate alerts | Unique disclosure key per watchlist |
| Partial refresh wipes data | Upsert only; never delete on failure |
| Dad stale external dir | Fundamentals from repo seed / explicit provider |
| Postgres FK on reload | Truncate/replace pattern (see `prices.py`) |
| Concurrent refresh | API mutex lock |

---

## Current status

| Phase | Status | Notes |
|-------|--------|-------|
| 1 | **Mostly done** | CRUD + UI shipped; Excel seed CLI pending |
| 2 | **Done** | Master → BSE → Yahoo pipeline, resolve API + UI |
| 3 | **Done** | CSV import, providers, computed snapshots, CLI |
| 4 | **Done** | Screener tab, column picker, sort, export, stale badges |
| 5 | **Done** | SAST/insider alerts filtered to watchlist BSE codes |
| 6 | **Done** | Unified refresh API, CLI, Windows script, mutex |
| 7 | **Done** | Export/import, health dashboard, golden tests, XBRL stub |

Last updated: 2026-08-10
