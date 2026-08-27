# Migration Rehearsal Runbook (Phase 8)

**Status:** Tooling complete — human rehearsal run required for gate sign-off.

Goal: dry-run the full cutover on an **isolated** database with real Samir + Julesh snapshots, resolve conflicts, import the canonical bundle, and verify counts/totals before Phase 9.

## Prerequisites

- [ ] Samir legacy Postgres dump or URL (`SAMIR_DATABASE_URL`)
- [ ] Julesh legacy Postgres dump or URL (`JULESH_DATABASE_URL`)
- [ ] Research tree available locally (`RESEARCH_DIR`, read-only)
- [ ] Feature branch: `feature/centralized-cloud-approval-workflow`
- [ ] Empty rehearsal target DB (`REHEARSAL_DATABASE_URL` or local Docker postgres)

## 1. Restore legacy snapshots (isolated)

Do **not** point at production. Use disposable Postgres instances:

```bash
# Example: restore dumps into local ports 5434 (Samir) and 5435 (Julesh)
export SAMIR_DATABASE_URL='postgresql+psycopg://pms:pms@localhost:5434/pms'
export JULESH_DATABASE_URL='postgresql+psycopg://pms:pms@localhost:5435/pms'
export REHEARSAL_DATABASE_URL='postgresql+psycopg://pms:pms@localhost:5436/pms_rehearsal'
```

Archive dumps with checksums before proceeding.

## 2. Reconcile (read-only)

```bash
uv run pms-platform reconcile-cutover \
  --samir-url "$SAMIR_DATABASE_URL" \
  --julesh-url "$JULESH_DATABASE_URL" \
  --research-dir "$RESEARCH_DIR" \
  --output-dir ./data/reconciliation \
  --fail-on-conflict
```

Review:

- `data/reconciliation/DATA_RECONCILIATION_REPORT.md`
- `data/reconciliation/reconciliation.json`
- `data/reconciliation/migration_bundle.json`

**Stop** if `value_conflict` rows exist. Record Samir's decision per conflict, fix legacy data or extend bundle policy, then re-run until `--fail-on-conflict` passes.

## 3. Prepare rehearsal target

```bash
export DATABASE_URL="$REHEARSAL_DATABASE_URL"
uv run pms-platform migrate --no-seed-users
```

## 4. Import canonical bundle

```bash
uv run pms-platform import-migration-bundle \
  --bundle ./data/reconciliation/migration_bundle.json \
  --bhav-source-url "$SAMIR_DATABASE_URL"
```

Only use `--bhav-source-url` when `nse_bhav_bars` reconciliation shows **identical** (no conflicts). Bhav is copied from Samir by default.

Dry-run first:

```bash
uv run pms-platform import-migration-bundle \
  --bundle ./data/reconciliation/migration_bundle.json \
  --dry-run
```

## 5. Verify counts and totals

Automatic verification runs at end of import. Re-run manually:

```bash
uv run pms-platform verify-rehearsal \
  --bundle ./data/reconciliation/migration_bundle.json \
  --bhav-source-url "$SAMIR_DATABASE_URL"
```

Checks: row counts per domain, qty sums by book, SCA bank balance, bhav bar count.

## 6. Approval workflow smoke (non-prod accounts)

```bash
export FEATURE_APPROVAL_WORKFLOW=1
docker compose up -d --build   # or Railway staging
```

1. Julesh: submit a **client qty** draft change.
2. Samir: approve from inbox.
3. Confirm official view updates; worker logs show job completion.

## 7. Storage capacity (500 MB gate)

```bash
uv run pms-platform rehearsal-capacity --research-dir "$RESEARCH_DIR"
```

Exit code 1 if combined private storage + Research Portfolio footprint exceeds ceiling (default 500 MB).

## 8. Backup and restore drill

**Local Docker:**

```bash
pg_dump "$REHEARSAL_DATABASE_URL" -Fc -f ./data/reconciliation/rehearsal_backup.dump
dropdb ... && createdb ...
pg_restore -d "$REHEARSAL_DATABASE_URL" ./data/reconciliation/rehearsal_backup.dump
uv run pms-platform verify-rehearsal --bundle ./data/reconciliation/migration_bundle.json
```

**Supabase staging (when available):** use dashboard backup → restore to branch → re-run verify.

## Phase 8 gate checklist

- [ ] `reconcile-cutover --fail-on-conflict` passes
- [ ] `import-migration-bundle` + `verify-rehearsal` pass
- [ ] Samir approval smoke test on rehearsal stack
- [ ] Backup restore drill succeeds
- [ ] `rehearsal-capacity` within 500 MB (or documented exception)
- [ ] All conflict decisions recorded in reconciliation report notes

## Related

- [`MIGRATION_RUNBOOK.md`](MIGRATION_RUNBOOK.md) — cutover sequence
- [`DEPLOYMENT_RUNBOOK.md`](DEPLOYMENT_RUNBOOK.md) — Railway/Supabase staging
- Phase 9 — production cutover (explicit authorization)
