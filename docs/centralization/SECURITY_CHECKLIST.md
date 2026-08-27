# Security Checklist (draft)

- [ ] Remove hard-coded production passwords from `auth/service.py` before cutover
- [ ] Rotate `AUTH_SECRET` at cutover
- [ ] `AUTH_COOKIE_SECURE=1` in production
- [ ] CSRF on cookie-authenticated mutations (Phase 3+)
- [ ] Rate limit login (Phase 12)
- [ ] No `NEXT_PUBLIC_*` secrets
- [ ] Supabase service role key backend-only
- [ ] Audit JSON redacts secrets
- [x] Dependency/secret scan in CI (Phase 7) — gitleaks in `.github/workflows/ci.yml`
- [ ] MFA documented as near-term requirement

See `CREDENTIAL_EXPOSURE_SCAN.md` for Phase 0 findings.
