# Architecture Decisions (Centralization)

| ID | Decision | Alternatives considered | Consequence |
|----|----------|----------------------|-------------|
| D1 | **Supabase Postgres** (Mumbai) as production DB | Firebase; per-PC Docker Postgres; Oracle VM Postgres | Relational data fits existing SQLAlchemy models; pooled + direct URLs |
| D2 | **One production DB** for all users | Per-user DBs; Excel sync | Eliminates Samir/Julesh drift |
| D3 | **Draft/approval overlays in same DB** | Separate draft DB; shadow Excel copies | Official vs My Working views via `ReadContext` |
| D4 | **FastAPI only privileged writer** | Browser → Supabase direct | Security; typed handlers; audit trail |
| D5 | **Railway** UI + API + worker | Oracle VM; Lightsail; local Docker prod | Faster deploy; three services from one repo |
| D6 | **Private object storage** for files (Supabase Storage) | Postgres BYTEA; OneDrive runtime | Keeps DB under 500 MB free tier |
| D7 | **Official / My Working / Proposal** read contexts | Per-route ad-hoc checks | Central overlay semantics |
| D8 | **Typed approval handlers** | Generic dynamic SQL on table names | Safe validation and atomic apply |
| D9 | **Postgres-backed job queue** initially | Redis; Celery | Fewer dependencies; `FOR UPDATE SKIP LOCKED` |
| D10 | **Excel import/export only after cutover** | Continue DailyEdit live reads | Ends formula-cache and per-PC workbook drift |
| D11 | **Pivot daily checkbox filter stays browser localStorage** | Firm-shared DB + Samir approval | Personal UI scope only; bhav/portfolio firms remain in Postgres |

## Explicit non-decisions (human reserved)

- Production Supabase/Railway project IDs and credentials
- Samir vs Julesh conflict resolution on business values
- Production cutover date and DNS
- Whether market-data imports may ever auto-approve
