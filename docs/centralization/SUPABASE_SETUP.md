# Supabase setup (Mumbai)

**Status:** Phase 7 — human creates project and pastes credentials into Railway (never commit values).

Region: **ap-south-1** (Mumbai), per `DECISIONS.md` D4.

## 1. Project

1. Create Supabase project (Pro recommended: always-on, PITR backups; Free tier pauses after 7 days idle).
2. Note **Project URL** and **service role key** (Settings → API). Service role is **backend-only** — never in Next.js or `NEXT_PUBLIC_*`.

## 2. Postgres connections

| Variable | Use | Endpoint |
|----------|-----|----------|
| `DATABASE_URL` | API + worker runtime | **Transaction pooler** (port **6543**, mode Transaction) |
| `DATABASE_DIRECT_URL` | `pms-platform migrate` / release task only | **Direct** (port **5432**) |

Connection string format (SQLAlchemy):

```
postgresql+psycopg://postgres.[project-ref]:[password]@aws-0-ap-south-1.pooler.supabase.com:6543/postgres?sslmode=require
```

Append `?sslmode=require` if the dashboard string omits it.

**Rules:**

- API and worker use the pooler URL only.
- Run migrations once per release via direct URL (`/migrate-entrypoint.sh` or `pms-platform migrate`).
- Do not run concurrent migrates from multiple API replicas.

## 3. Storage buckets (private)

Create **private** buckets (Storage → New bucket → public off):

| Bucket | Purpose |
|--------|---------|
| `source-files` | Staged import uploads, immutable versions |
| `exports` | Generated export artifacts |

Wire bucket names in env when `FEATURE_CLOUD_STORAGE=1` (adapter swap from local `PRIVATE_STORAGE_DIR` is a follow-up; buckets should exist before cutover).

RLS: default deny; access via service role from API/worker only.

## 4. Backups

- Enable daily logical backups (Pro) or export before cutover.
- Record backup id + timestamp in cutover checklist.

## 5. Staging verification

```bash
# From laptop with DATABASE_DIRECT_URL set:
uv run pms-platform migrate
uv run pms-platform create-user --email you@example.com --name You --role admin
```

Then point Railway API/worker at pooler `DATABASE_URL` and run smoke tests from `DEPLOYMENT_RUNBOOK.md`.

## 6. Not in scope for agents

- Creating the Supabase org/billing account
- Rotating production passwords (Phase 9)
- Importing reconciliation bundle (Phase 8/9)

See also: `DEPLOYMENT_RUNBOOK.md`, `ROLLBACK_RUNBOOK.md`, `SECURITY_RUNBOOK.md`.
