# Deployment Runbook

**Status:** Phase 7 complete — staging deploy when Supabase + Railway credentials are provided. **No production cutover without explicit authorization.**

## Architecture

| Service | Host | Image | Public |
|---------|------|-------|--------|
| **ui** | Railway | `app/Dockerfile` | Yes — single hosted URL |
| **api** | Railway | root `Dockerfile` | No — UI proxies `/backend` |
| **worker** | Railway | root `Dockerfile`, `/worker-entrypoint.sh` | No |
| **postgres** | Supabase Mumbai | managed | No |
| **storage** | Supabase private buckets | managed | No |

Detailed Railway steps: [`deploy/railway/README.md`](../../deploy/railway/README.md).  
Supabase: [`SUPABASE_SETUP.md`](SUPABASE_SETUP.md).

## Local full stack (unchanged)

```bash
docker compose up -d --build   # postgres + api + worker + ui
```

Local API migrates on start (`RUN_MIGRATIONS_ON_START=1` default). Worker does not migrate.

## Release migration (production)

**Once per schema change**, before or as part of deploy — not on every API boot:

```bash
# Railway one-shot (uses DATABASE_DIRECT_URL from service env)
railway run --service api /migrate-entrypoint.sh

# Or locally / CI against staging direct URL:
DATABASE_DIRECT_URL='postgresql+psycopg://...' uv run pms-platform migrate
```

Skip builtin user seed in prod if users already exist:

```bash
pms-platform migrate --no-seed-users
```

Alembic head is verified in CI (`test_watchlist_migrations_are_chained_to_head`).

## Environment variables

See [`.env.example`](../../.env.example) cloud section. Minimum production set:

- `DATABASE_URL` (pooler)
- `DATABASE_DIRECT_URL` (direct, migrate task only)
- `RUN_MIGRATIONS_ON_START=0`
- `AUTH_SECRET`, `AUTH_DISABLED=0`, `AUTH_COOKIE_SECURE=1`
- `FEATURE_APPROVAL_WORKFLOW=1`
- Feature flags per cutover checklist (`LEGACY_EXCEL_*` off in prod)

## Deploy sequence (staging)

1. Create Supabase project + buckets ([`SUPABASE_SETUP.md`](SUPABASE_SETUP.md)).
2. Create Railway project + three services ([`deploy/railway/README.md`](../../deploy/railway/README.md)).
3. Set env vars on API and worker (shared); UI gets `API_INTERNAL_URL` pointing at API private hostname.
4. Run **migrate one-shot** with `DATABASE_DIRECT_URL`.
5. Deploy API → worker → UI (or parallel after migrate).
6. Create users: `railway run --service api pms-platform create-user ...`
7. Smoke: login, `/health`, draft qty → approve → official view.
8. Monitor worker logs for outbox/import jobs.

## CI gate (no cloud creds required)

GitHub Actions (`.github/workflows/ci.yml`):

- Ruff + pytest (minus 2 known pre-existing failures)
- Migration chain test
- Next.js production build
- Docker build API + UI
- Gitleaks secret scan

## Blocked without human action

- Production DNS / cutover date
- Credential values in git or this doc
- Phase 8 reconciliation rehearsal on real legacy DBs
- Phase 9 merge to `main` and flag flip

## Related

- [`ROLLBACK_RUNBOOK.md`](ROLLBACK_RUNBOOK.md)
- [`SECURITY_RUNBOOK.md`](SECURITY_RUNBOOK.md)
- [`MIGRATION_RUNBOOK.md`](MIGRATION_RUNBOOK.md)
- Master plan Phase 7–9
