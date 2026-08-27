# Centralization Implementation Status

Branch: `feature/centralized-cloud-approval-workflow`  
Master plan: [`../CURSOR_CENTRALIZATION_MASTER_PLAN.md`](../CURSOR_CENTRALIZATION_MASTER_PLAN.md)

| Phase | Status | Evidence | Remaining work |
|-------|--------|----------|----------------|
| 0 — Repository audit and baseline | complete | `docs/centralization/AS_IS_ARCHITECTURE.md`, `CREDENTIAL_EXPOSURE_SCAN.md`, baseline pytest | None |
| 1 — Architecture seams and feature flags | complete | `read_context.py`, `feature_flags.py`, config, `.env.example`, `TARGET_ARCHITECTURE.md`, `DECISIONS.md` | None |
| 2 — Schema and approval engine | complete | Migration `x1y2z3a4b5c6`, models, `approval/service.py`, handler registry, `test_approval_service.py` | Domain handlers beyond client qty (Phase 5) |
| 3 — Working/official APIs and UI | complete | `client_positions` migration, view-aware dashboard, `/change-requests` API, qty PATCH, Official/My Working UI, draft tray, approvals inbox | Enable `FEATURE_APPROVAL_WORKFLOW=1` locally to exercise; production deploy still blocked |
| 4 — Incremental jobs, storage and imports | complete | `storage/adapter.py`, source lineage migration, `staged_import.py`, job worker + outbox, `/imports/staged` API, `test_staged_import.py` | Domain DB writes on apply deferred to Phase 5 |
| 5 — Domain migrations | complete | Client + SCA qty approval; Charts DB; bhav auto; staged Research imports; client index/mcap + SCA bank in DB | — |
| 6 — Reconciliation tooling | in_progress | `reconcile-cutover` CLI, JSON + markdown reports, domain comparators | Research row-level diff, migration bundle export |
| 7 — Deployment preparation | not_started | — | Railway/Supabase runbooks (no prod deploy without auth) |
| 8 — Migration rehearsal | not_started | — | — |
| 9 — Production cutover | blocked | — | Requires human credentials + explicit authorization |
| 10 — Cleanup after stabilization | not_started | — | After Phase 9 sign-off |

## Baseline test results (Phase 0)

Run: `uv run pytest -q` on branch `feature/centralized-cloud-approval-workflow`

- **282 passed** (includes 10 new centralization tests), 2 failed (pre-existing)
- 1 deprecation warning (`httpx` / Starlette TestClient)

| Test | Failure |
|------|---------|
| `tests/test_masters.py::test_apply_appends_transaction_and_updates_security` | Pre-existing |
| `tests/test_migrations_watchlist.py::test_watchlist_migrations_are_chained_to_head` | Fixed — head now `x1y2z3a4b5c6` |
| `tests/test_pivot_bhav.py::test_prune_keeps_only_20_sessions` | Prune count assertion |

## Dirty worktree (Phase 0)

- Untracked: `docs/CURSOR_CENTRALIZATION_MASTER_PLAN.md` (added to branch)
- No unrelated staged changes on feature branch at audit time

## Human blockers (reserved)

- Supabase / Railway project credentials
- Production deploy / migrate authorization
- Samir vs Julesh business-value conflict resolution
- Production password rotation timing
- DNS / cutover date
