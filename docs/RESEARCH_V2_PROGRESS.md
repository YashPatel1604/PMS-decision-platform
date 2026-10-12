# Research V2 progress

## Phase

Both Ask Grok and the full brief, when a company is selected, use only pages linked to that company. Ask stays near 3,000 input tokens and 500 output tokens. The full brief stays near 4,000 input tokens and 1,000 output tokens. Loading Research still does not call Grok. Migrations from earlier slices are still not applied to production.

## Assumptions verified in code

- Stack is FastAPI + Next.js + PostgreSQL. Research UI is `/research`. Model default is `grok-4.20-0309-non-reasoning` in `src/pms_platform/config.py`.
- Grok is called only from `generate_research_brief` and `generate_research_ask`, reached by `POST /research/brief`, `POST /research/ask`, `POST /research/coverage/run` when `dry_run=false`, and the matching CLI commands.
- `investment_theses.status = active` means the latest saved version. The company page labels that “approval not confirmed.”
- There is no Postgres RLS. Role `client` cannot call `/research`.
- Railway persistence of `/data/uploads` is still unknown. The company page says the original file cannot be opened in the browser.
- Existing indexed documents are not listed as new. There is no review cutoff yet.

## Files changed

- `app/src/app/research/page.tsx`
- `app/src/app/research/company/[securityId]/page.tsx`
- `app/src/components/research-page-client.tsx`
- `app/src/components/research-home.tsx`
- `app/src/components/research-company-view.tsx`
- `app/src/components/research-analyst-view.tsx`
- `app/src/lib/api.ts`
- `src/pms_platform/documents/coverage.py`
- `src/pms_platform/api/routes/research.py`
- `tests/test_research_analyst.py`

## Migrations

`g0h1i2j3k4l5_research_reviews` adds `research_reviews`. `h1i2j3k4l5m6_thesis_approval` adds `approved_by`, `approved_at`, and one-approved-thesis index. Neither is applied to production. Existing saved theses are not backfilled as approved.

## Tests run

`npx tsc --noEmit` in `app/` passed. `python3 -m py_compile` passed for the Python edits. `pytest` did not start: reading `.venv` `entry_points.txt` on OneDrive timed out. The new test is `test_company_overview_is_local_and_unapproved`.

## Next

P0 research behavior is in the branch. Apply the two migrations on Railway before review and thesis approval are used there. Do not start P1 (assumption extraction, DOCX, OneDrive delta) unless asked.
