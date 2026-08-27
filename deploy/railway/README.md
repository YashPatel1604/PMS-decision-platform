# Railway deployment (Phase 7)

One GitHub repo, **three Railway services**. Do not deploy to production without explicit authorization (see `docs/centralization/DEPLOYMENT_RUNBOOK.md`).

## 1. Create project

1. New Railway project (e.g. `pms-decision-platform-staging`).
2. Connect the GitHub repo; deploy from branch `feature/centralized-cloud-approval-workflow` for staging, `main` after merge.

## 2. API service

| Setting | Value |
|---------|--------|
| Root directory | `.` (repo root) |
| Dockerfile | `Dockerfile` |
| Start command | *(default)* `/api-entrypoint.sh` |
| Public networking | **Off** (UI proxies `/backend`) |
| Health check | `GET /health` |

**Required env** (from Supabase + secrets):

- `DATABASE_URL` — Supabase **pooler** (port 6543, `?sslmode=require`)
- `DATABASE_DIRECT_URL` — Supabase **direct** (port 5432, migrations only)
- `RUN_MIGRATIONS_ON_START=0`
- `AUTH_SECRET` — strong random (32+ bytes)
- `AUTH_COOKIE_SECURE=1`
- `AUTH_DISABLED=0`
- `FEATURE_APPROVAL_WORKFLOW=1` (staging/cutover)
- `FEATURE_CLOUD_STORAGE=1` (when Supabase buckets wired)
- `FEATURE_LEGACY_EXCEL_READ=0` / `FEATURE_LEGACY_EXCEL_WRITE=0` (production)
- `PRIVATE_STORAGE_DIR=/data/uploads/private`
- `CORS_ORIGINS` — Railway UI public URL if needed

**Release migrations** (before each deploy that changes schema):

```bash
railway run --service api /migrate-entrypoint.sh
# or: railway run --service api pms-platform migrate
```

Use `DATABASE_DIRECT_URL` on the migrate task.

## 3. Worker service

| Setting | Value |
|---------|--------|
| Root directory | `.` |
| Dockerfile | `Dockerfile` |
| Start command | `/worker-entrypoint.sh` |
| Public networking | **Off** |

Copy the same env as API (except no health check). `RUN_MIGRATIONS_ON_START` not used.

Optional: `WORKER_ID=worker-1` if scaling later (single worker initially per D5).

## 4. UI service

| Setting | Value |
|---------|--------|
| Root directory | `app` |
| Dockerfile | `Dockerfile` |
| Start command | *(default)* `node server.js` |
| Public networking | **On** — this is the hosted URL |

**Build args / env:**

- `NEXT_PUBLIC_API_URL=/backend`
- `API_INTERNAL_URL` — Railway **private** URL of the API service (e.g. `http://api.railway.internal:8000` or the generated internal hostname)

Generate domain on UI service only.

## 5. Service references

In Railway, add a **service reference** from UI → API so `API_INTERNAL_URL` resolves on the private network.

## 6. Staging smoke

1. Run migrate one-shot.
2. Deploy API + worker + UI.
3. Open UI URL → login → `/health` via UI proxy returns OK.
4. Submit a draft qty change → approve → verify official view updates.
5. Check worker logs for job completion.

## Files in this folder

- `api.railway.toml` — optional config snippet for API
- `worker.railway.toml` — worker start override
- `ui.railway.toml` — UI root + Dockerfile path

Railway may ignore `railway.toml` when settings are configured in the dashboard; these files document the intended shape.
