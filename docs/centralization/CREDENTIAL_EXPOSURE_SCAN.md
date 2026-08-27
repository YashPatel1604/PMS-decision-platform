# Credential Exposure Scan (Phase 0)

Scan date: 2026-08-28  
Scope: `pms-decision-platform` on branch `feature/centralized-cloud-approval-workflow`

**No secret values are reproduced in this document.**

## Findings (action required before production cutover)

| Location | Issue | Severity | Remediation phase |
|----------|-------|----------|-------------------|
| `src/pms_platform/auth/service.py` | Hard-coded `_LOCAL_USERS` with plaintext passwords synced on startup | High | Phase 12 / cutover runbook — remove defaults; provision via secure CLI only |
| `tests/test_auth_service.py` | Test fixtures reference same passwords | Medium | Replace with generated fixtures; never use production passwords in tests |
| `tests/test_auth_api.py` | Test user creation | Low | Use fake credentials only |
| `.env.example` | Placeholder `AUTH_SECRET` and `POSTGRES_PASSWORD=pms` | Medium | Document must-change; never use in production |
| `docker-compose.yml` | Default `AUTH_SECRET` and `POSTGRES_PASSWORD` fallbacks | High | Production compose must require explicit env; no defaults |
| `docs/WINDOWS_DAD_SETUP.md`, `docs/WINDOWS_NEW_PC_INSTALL.md` | May reference login usernames | Low | Remove password references; point to secure provisioning |
| `.env` (local, gitignored) | May contain real paths | Info | Never commit |

## Not found in tracked source

- Supabase service-role keys
- Railway tokens
- AWS/GCP credentials
- `NEXT_PUBLIC_*` database secrets (correct — none exposed to browser)

## Mandatory cutover steps (from master plan)

1. Rotate `AUTH_SECRET` and all user passwords before production.
2. Remove or gate `ensure_builtin_users` plaintext sync for production `APP_ENV`.
3. Run secret scan in CI (Phase 7).
4. Do **not** rewrite Git history without explicit human approval.

## Scan commands used

```bash
rg -n "password|AUTH_SECRET|POSTGRES_PASSWORD|service.role|SUPABASE" --glob '*.{py,md,env*,yml,sh,tsx,ts}'
rg -n "samir@|julesh@" --glob '*.{py,md,tsx,ts}'
```
