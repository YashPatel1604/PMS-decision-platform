# Rollback Runbook

Use when a hosted deploy causes data loss, auth failure, or incorrect official state. **Human authorization required for production.**

## 1. Stop the bleed (< 5 min)

1. Set Railway feature flags off on API + worker (redeploy with env):
   - `FEATURE_APPROVAL_WORKFLOW=0`
   - `FEATURE_CLOUD_STORAGE=0`
   - `FEATURE_LEGACY_EXCEL_READ=1` / `FEATURE_LEGACY_EXCEL_WRITE=1` if reverting to local Excel workflow temporarily
2. Scale worker to 0 or stop worker service (stops new job side effects).
3. Announce freeze to Samir/Julesh — no new edits until state is verified.

## 2. Revert application (< 15 min)

1. Railway → each service → **Deployments** → rollback to last known-good image/deployment id.
2. If rollback includes a **downgrade** migration, do **not** auto-run migrate — schema downgrade requires explicit Alembic downgrade plan (usually restore DB instead).
3. Confirm UI loads and `/backend/health` returns OK.

## 3. Database restore (if schema or data bad)

1. Identify last verified backup (Supabase dashboard or pre-cutover dump).
2. Restore to a **new** Supabase branch/instance if possible; test before swapping `DATABASE_URL`.
3. Point API + worker at restored instance; run smoke tests.
4. Document incident: time, backup id, who approved restore.

## 4. Legacy local fallback

If cloud is down but cutover not complete:

1. Local Docker archives remain read-only backups — do not delete.
2. Samir/Julesh can use local `main` Docker until cloud is healthy (per operational agreement).
3. Re-run `reconcile-cutover` before any re-attempt.

## 5. Post-rollback

- [ ] Root cause recorded (deploy, migration, conflict resolution, worker job).
- [ ] Secrets rotated if compromise suspected (`SECURITY_RUNBOOK.md`).
- [ ] Blocking conflicts re-resolved before next cutover attempt.

## Do not

- Delete legacy Postgres dumps or Research/DailyEdit archives.
- Re-run `migrate` concurrently from multiple services.
- Force-push production git branches.

See [`DEPLOYMENT_RUNBOOK.md`](DEPLOYMENT_RUNBOOK.md) and master plan Phase 9 for forward path after stabilization.
