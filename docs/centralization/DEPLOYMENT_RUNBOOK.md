# Deployment Runbook (draft)

**Status:** Phase 7 — requires Supabase + Railway credentials (human-provided).

## Services (Railway)

1. **ui** — Next.js, public URL
2. **api** — FastAPI, internal
3. **worker** — same image, `worker` entrypoint, no public port

## Supabase (Mumbai)

- Create project (Pro recommended for always-on + backups; Free pauses after 7 days inactivity)
- Enable connection pooler for `DATABASE_URL`
- Use direct connection for `DATABASE_DIRECT_URL` migrations only
- Create private storage buckets for source files and exports

## Release migration

Run once per release (not on every API startup in production):

```bash
alembic upgrade head
```

Use `DATABASE_DIRECT_URL` when configured.

## Not authorized in this branch

- No production deploy without explicit human approval
- No credential values in this document
