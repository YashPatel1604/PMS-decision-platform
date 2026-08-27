# Security Runbook (Phase 7)

Operational security for hosted deployment. Complements `SECURITY_CHECKLIST.md` and `CREDENTIAL_EXPOSURE_SCAN.md`.

## Secrets inventory

| Secret | Where | Never |
|--------|-------|-------|
| `AUTH_SECRET` | Railway API + worker | Client, UI build args |
| `DATABASE_URL` | Railway API + worker | Browser, logs |
| `DATABASE_DIRECT_URL` | Migrate one-shot only | API runtime env |
| `SUPABASE_SERVICE_ROLE_KEY` | API + worker (when cloud storage on) | UI, git |
| `POSTGRES_PASSWORD` | Local Compose only | Production |

Rotate all defaults before any non-local deploy.

## Pre-deploy

1. `AUTH_DISABLED=0`, strong `AUTH_SECRET` (32+ random bytes).
2. `AUTH_COOKIE_SECURE=1` on HTTPS UI.
3. `RUN_MIGRATIONS_ON_START=0` on API — migrations via one-shot task only.
4. API service **not** public; only UI has a public URL.
5. CORS: `CORS_ORIGINS` lists UI origin only.
6. CI: gitleaks on push/PR (`.github/workflows/ci.yml`).

## Runtime

- Session cookies: HttpOnly (existing auth middleware).
- Audit events must not log passwords, tokens, or full file blobs.
- Staged imports: checksum + lineage in Postgres; blobs in private buckets.
- Worker has same DB credentials as API — no extra attack surface if API is private.

## Incident response

1. **Suspected credential leak** — rotate `AUTH_SECRET`, Supabase DB password, service role key; invalidate sessions (redeploy API).
2. **Unauthorized data change** — check `audit_events` + `change_requests`; rollback per `ROLLBACK_RUNBOOK.md`.
3. **Migration failure** — stop deploys; restore Postgres from last verified backup; do not re-run migrate until root cause is known.

## Post-cutover (Phase 9)

- Remove hard-coded builtin passwords from `auth/service.py` (checklist item).
- Document MFA as near-term requirement for Samir/Julesh/Yash accounts.
- Rate-limit login (deferred — track in master plan Phase 12).

## Verification

```bash
# No secrets in tracked files (local)
gitleaks detect --source . --verbose

# Health should not echo secrets
curl -s https://<ui>/backend/health | jq .
```

Human sign-off required before production cutover.
