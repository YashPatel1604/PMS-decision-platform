# Phase 8 Rehearsal Results

**Date:** 2026-08-28  
**Branch:** `feature/centralized-cloud-approval-workflow`  
**Canonical source:** Yash PC (`localhost:5433/pms`) — Samir/Julesh PCs assumed identical baseline ([D13](DECISIONS.md)).

## Reconciliation

| Check | Result |
|-------|--------|
| `reconcile-cutover --fail-on-conflict` | **Pass** (0 value conflicts) |
| Samir/Julesh inputs | Same DB URL (single canonical snapshot) |
| Research dir | `/Users/yash/Library/CloudStorage/OneDrive-Personal/Research` |
| Research note | Security Master workbook has 75 names; DB has 177 securities — informational only (`only_in_research`) |

## Migration bundle import → `pms_rehearsal`

| Domain | Rows |
|--------|------|
| securities | 177 |
| pivot_portfolio_symbols | 101 |
| watchlist_members | 139 |
| client_positions | 1 (client qty sum 3,870) |
| nse_bhav_bars | 84,561 (copied from canonical) |
| charts_range_rows | 0 |
| client_book_settings | 0 |

`import-migration-bundle` + `verify-rehearsal`: **all checks passed**.

## Backup / restore drill

| Step | Result |
|------|--------|
| `pg_dump -Fc pms_rehearsal` | 4.2 MB → `data/reconciliation/dumps/rehearsal-backup.dump` |
| Drop + recreate + `pg_restore` | OK |
| `verify-rehearsal` post-restore | **Pass** |

## Automated approval tests

`pytest` approval suite (service + API + SCA): **17 passed**.

## Capacity note

`rehearsal-capacity` reports ~5 GB (full `Research/Portfolio` tree on disk). Expected for local OneDrive archive. Cloud runtime uses private staged uploads only — not a cutover blocker.

## Optional human step (not blocking tooling)

- [ ] Samir logs into local Docker UI, approves one test **client qty** draft from Julesh (2-minute browser smoke)

## Artifacts (local, gitignored)

- `data/reconciliation/dumps/yash-canonical.dump` (19 MB)
- `data/reconciliation/dumps/rehearsal-backup.dump` (4.2 MB)
- `data/reconciliation/migration_bundle.json`
- `data/reconciliation/reconciliation.json`

## Phase 8 gate

| Criterion | Status |
|-----------|--------|
| Reconciliation with zero unexplained Samir/Julesh conflicts | Done (single source) |
| Bundle import + verify | Done |
| Backup restore drill | Done |
| Approval path (automated) | Done |
| Samir browser smoke | Optional — user |

Ready for Phase 9 when Supabase/Railway credentials and explicit cutover authorization are provided.
