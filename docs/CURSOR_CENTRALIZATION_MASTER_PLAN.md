# PMS Decision Platform — Cursor Centralization Master Plan

## How to use this file

EVERYTHING GETS PUSHED TO A NEW BRANCH ON GITHUB NOT ON MAIN. I STILL NEED MAIN TO RUN AND STILL IT MIGHT NEED MAINTAINANCE SO MAIN DOESNT CHANGE. ALL UPDATES GO TO A NEW BRANCH.

Open the `PMS-decision-platform` repository in Cursor, create a feature branch named `feature/centralized-cloud-approval-workflow`, open Cursor Agent mode, and paste everything between **BEGIN CURSOR MASTER PROMPT** and **END CURSOR MASTER PROMPT**.

This is a finite implementation program. Cursor must complete each phase once, run the stated verification, and update the status file. It must not create an open-ended “repeat until perfect” loop.

---

# BEGIN CURSOR MASTER PROMPT

You are the lead engineer responsible for centralizing the PMS Decision Platform, a private portfolio-management application currently run separately on multiple computers. Work through this program autonomously and in order. Inspect the repository before making assumptions, preserve working behavior, make small reviewable commits, and stop only for a genuine external blocker such as missing cloud credentials, an irreversible production action, or a data conflict that requires a human decision.

Do not merely write a plan. Implement the code, migrations, tests, documentation, local deployment configuration, reconciliation tools, and production runbooks required by this prompt.

## 1. Non-negotiable outcome

Build one centralized online production system with:

- One hosted Next.js user interface.
- One hosted FastAPI API.
- One hosted background worker.
- One shared Supabase Postgres production database in the Mumbai region.
- One private Supabase Storage area for source files, staged imports, immutable research, exports, and file-version metadata.
- Railway as the initial hosting target for the UI, API, and worker.
- GitHub as the code source and deployment trigger only.
- Local Docker retained only for development and testing.
- No separate production database for Samir, Julesh, or Yash.
- No live production dependency on a user’s laptop, OneDrive mount, local Docker volume, DailyEditFiles directory, or browser localStorage.

The production site must remain available when all three users’ computers are switched off.

## 2. Required business-control model

There is one shared database, but not every user may directly alter approved firm data.

### Roles

- **Samir — business approver/admin:** sole approver of firm-affecting business-data changes. Can propose changes, review all submitted requests, approve, reject, and administer operational users. A change Samir makes must still pass through an explicit confirmation screen and be audited as self-proposed/self-approved.
- **Julesh — portfolio contributor:** can view approved data, create and edit drafts, submit change requests, see his own working view immediately, revise or withdraw eligible requests, upload source files into staging, and review rejection reasons. Cannot approve or directly mutate approved firm data.
- **Yash — technical owner/contributor:** can administer deployment and code, view operational diagnostics, and propose firm-data changes. Cannot bypass Samir’s business approval merely because he has technical access. Technical database migrations and system maintenance are distinct from business-data approval.
- **Future viewer:** read-only access to explicitly assigned approved data. Do not implement multi-tenant client isolation beyond what the existing application needs unless the repository already supports it, but keep the authorization model extensible.

Do not conflate an application role with a raw Postgres role. Browser users never receive a privileged database credential.

### Two views of the same database

Implement these views consistently across all affected screens and calculations:

1. **Official view** — approved canonical data only. This drives official reports, shared totals, approved holdings, alerts, exports, and analytics.
2. **My Working view** — the approved baseline overlaid with the current user’s draft and submitted changes. This lets Julesh immediately see the quantities, valuations, chart calculations, pivots, watchlists, and other results produced by his own proposed edits before Samir approves them.

Samir must also be able to preview any submitted change request exactly as its proposer sees it.

Pending or draft data must never leak into official calculations, materialized caches, exports, alerts, or API responses that request Official view.

### Change lifecycle

Use the following finite state machine:

`draft -> submitted -> approved`

`draft -> withdrawn`

`submitted -> rejected`

`submitted -> withdrawn` only if review has not started and business rules allow it

`submitted -> conflict` if the approved row changed after the proposal’s recorded base version

`rejected/conflict -> new draft revision` rather than mutating historical records

Approved, rejected, withdrawn, and superseded records are immutable historical evidence.

### Expected user experience

Example: approved quantity is 1,000 and Julesh changes it to 1,200.

- Julesh immediately sees `1,200` in My Working view with a visible Draft or Pending Approval badge.
- Julesh can switch to Official view and still see `1,000`.
- Until submission, Samir is not required to see Julesh’s incomplete draft in the approval inbox.
- After Julesh submits, Samir sees `1,000 approved -> 1,200 proposed`, the proposer, timestamp, reason, validation results, and calculated impact.
- Official calculations continue using 1,000 until approval.
- Samir can preview the full portfolio using 1,200 before deciding.
- Approval atomically makes 1,200 official for everyone.
- Rejection removes the overlay from Julesh’s active working view and preserves the rejected request and reason in history.

## 3. Current-system facts to preserve

Before editing, inspect the repository and verify the actual implementation of these facts. Document any discrepancy rather than silently assuming the prompt is wrong.

### Existing deployment

- The application is currently FastAPI + Next.js + Postgres under Docker Compose.
- Each local computer currently has a separate Postgres volume and therefore divergent data.
- The UI proxies API requests under `/backend`.
- Authentication currently uses HTTP-only session cookies and invite-only users.
- Samir’s and Julesh’s current local installations must eventually become non-production.

### Existing storage layers

- `Research/` is the permanent historical knowledge base and is read-only to the current application.
- `DailyEditFiles/` contains writable operational Excel copies and is not reliably synchronized.
- Browser localStorage currently holds some pivot/chart state.
- GitHub synchronizes code, not operational data.

### Existing functional behavior

Preserve these behaviors unless tests or code inspection prove they have intentionally changed:

- Client Portfolio positions currently come from the Model workbook while live Price, Value, Percent, and Total are derived from the selected as-of bhav close.
- Market capitalization is derived using a stored/parsed mcap factor multiplied by bhav close; `%Firm` depends on Stocks quantity, bhav, and market capitalization.
- SCA LLP includes quantity, blocked quantity, and cash/bank balance semantics.
- Chart Range high/low, weekly support/resistance, close overrides, Fibonacci/correction calculations, and correction-percentage settings must retain their business meaning.
- Pivot selected symbols have explicit order and metadata; `LIQUIDCASE` is hidden from the Pivot UI.
- Watchlists are firm-shared rather than isolated per user.
- Bhav data is the shared price source and imports must retain validate-then-commit behavior.
- Transactions, investment episodes, decision events, portfolio snapshots, fundamentals, valuation data, and provenance diagnostics already live in Postgres and should be migrated rather than redesigned without cause.
- Research transaction masters, snapshots, Security Master data, market files, corporate actions, dividends, and benchmarks retain provenance.
- Heavy global refresh must be replaced with incremental, idempotent jobs where possible, but analytical results must not regress.

### Security warning

The existing documentation may contain real seeded passwords. Never repeat them in new files, logs, fixtures, screenshots, commits, or output. Locate credential-like strings, remove hard-coded defaults from active code and documentation, create placeholder-only examples, and add a mandatory credential-rotation step to the cutover runbook. Do not rewrite Git history or rotate live credentials without explicit human confirmation.

## 4. Engineering operating rules

Follow these rules for the entire implementation:

1. Start with read-only repository inspection: tree, services, models, migrations, routes, authentication, workbook parsers, caches, jobs, tests, Docker, and deployment docs.
2. Read and obey any `AGENTS.md`, repository instructions, or existing architecture decisions.
3. Preserve unrelated user changes and dirty-worktree content.
4. Use existing frameworks and conventions unless a change is necessary and documented.
5. Keep Alembic or the repository’s existing migration framework as the only production-schema authority. Do not make undocumented dashboard-only schema changes.
6. Never place a database password, service-role key, session secret, or cloud token in source control or browser bundles.
7. Do not allow the frontend to issue privileged writes directly to Supabase.
8. All firm-data writes pass through FastAPI domain services and the approval engine.
9. Do not implement approval by accepting arbitrary table names and executing dynamic SQL. Use a registry of typed domain handlers with explicit validation and application logic.
10. Apply an approved multi-operation change set in one database transaction: all changes succeed or none do.
11. Use optimistic concurrency. Every mutable approved entity must have a row version or equivalent concurrency token.
12. Add idempotency keys to imports, jobs, approval actions, and other retryable mutations.
13. Use UTC timestamps in storage and display India time where appropriate.
14. Use decimal/numeric types for financial values; never introduce binary floating-point errors into quantities, prices, percentages, cash, returns, or valuation calculations.
15. Do not create an infinite repair loop. A failing command may be retried at most twice after a reasoned code/configuration change. If still failing, record the blocker, evidence, attempted fixes, and exact next action.
16. Do not deploy, migrate, or modify production resources until a human explicitly provides the required credentials and authorizes the production action.
17. Do not delete local databases or Excel files during cutover. Archive and checksum them first.
18. Prefer reversible changes and feature flags during migration.
19. Do not mark a phase complete merely because code was written; meet its verification gate.
20. Do not ask the user questions that can be answered by inspecting the repository.

## 5. Required implementation-tracking files

Create and maintain these documents:

- `docs/centralization/AS_IS_ARCHITECTURE.md`
- `docs/centralization/TARGET_ARCHITECTURE.md`
- `docs/centralization/DECISIONS.md`
- `docs/centralization/IMPLEMENTATION_STATUS.md`
- `docs/centralization/DATA_AUTHORITY_MATRIX.md`
- `docs/centralization/DATA_RECONCILIATION_REPORT.md`
- `docs/centralization/MIGRATION_RUNBOOK.md`
- `docs/centralization/DEPLOYMENT_RUNBOOK.md`
- `docs/centralization/ROLLBACK_RUNBOOK.md`
- `docs/centralization/SECURITY_CHECKLIST.md`
- `docs/centralization/ACCEPTANCE_REPORT.md`

`IMPLEMENTATION_STATUS.md` must have one row per phase with `not_started`, `in_progress`, `blocked`, or `complete`, plus evidence and remaining work. Update it at the start and end of every phase.

`DECISIONS.md` must record architecture decisions, alternatives considered, and consequences. At minimum record:

- Supabase Postgres instead of Firebase.
- One production DB rather than per-user DBs.
- Draft/approval overlays within the same DB rather than per-user databases.
- FastAPI as the only privileged writer.
- Railway UI/API/worker topology.
- Private object storage for files rather than database BLOBs.
- Official vs My Working read contexts.
- Typed approval handlers rather than generic dynamic SQL.
- Postgres-backed job queue initially rather than adding Redis.
- Excel as import/export only after cutover.

## 6. Target data architecture

Retain existing canonical domain tables where appropriate. Add or adapt the following concepts using repository naming conventions.

### Identity and authorization

Add explicit application authorization data such as:

- `users` or existing user table
- `user_roles`
- `role_permissions` if the existing model warrants normalized permissions
- `sessions` if sessions are database-backed

Required application permissions include:

- `view_approved_data`
- `create_draft_changes`
- `submit_changes`
- `withdraw_own_changes`
- `view_own_working_data`
- `view_all_submitted_changes`
- `preview_submitted_changes`
- `approve_business_changes`
- `reject_business_changes`
- `manage_operational_users`
- `view_system_diagnostics`
- `manage_deployments` as an operational distinction, not necessarily a database permission

Only Samir receives `approve_business_changes` in production seed/configuration. Do not rely only on a username literal inside route code; model the permission explicitly, while ensuring production provisioning assigns it only to Samir.

### Change requests

Implement equivalent normalized tables:

#### `change_requests`

- UUID primary key
- Human-readable title and optional reason
- Domain/scope
- Proposer user ID
- Status enum/check constraint
- Base approved revision/snapshot identifier
- Created, updated, submitted, reviewed timestamps
- Reviewer user ID
- Review note/rejection reason
- Conflict explanation
- Impact summary JSON generated by validated domain logic
- Monotonic request version
- Optional superseded-request reference

#### `change_operations`

- UUID primary key
- Change-request foreign key
- Stable operation order
- Typed domain/entity kind
- Target entity ID or typed natural key for a create
- Operation type: insert/update/delete/domain_action
- Base row version
- Redacted/safe before-state JSON
- Proposed after-state JSON
- Validation result JSON
- Schema/payload version

These JSON payloads are evidence and transport for typed handlers. They are not permission to update arbitrary database objects.

#### `audit_events`

- UUID primary key
- Actor user ID
- Action/event type
- Entity kind and ID
- Change-request ID when applicable
- Request/correlation ID
- Before and after JSON with secret-field redaction
- UTC timestamp
- Source IP/user agent if already supported and privacy-appropriate

Audit events are append-only through the application. Normal application roles must not update or delete them.

### Concurrency

Add `row_version`, `updated_at`, and `updated_by` to mutable approved entities where absent. An update increments `row_version` atomically. Approval must compare every proposed operation’s `base_row_version` with the current approved row. Any mismatch prevents the entire change set from applying and marks or returns a conflict requiring review.

Never silently rebase a financial change.

### Working-view read context

Create one centralized abstraction, named according to project conventions, equivalent to:

`ReadContext(mode=official|mine|proposal, viewer_user_id, change_request_id=None)`

All affected repositories/services/calculators must receive this context rather than scattering role checks throughout routes and UI components.

- `official`: canonical approved rows only.
- `mine`: canonical rows plus the viewer’s active draft and submitted operations, applied deterministically.
- `proposal`: canonical rows plus one selected submitted request, available only to authorized reviewers or its proposer.

For the initial three-user scale, applying validated overlays in the domain/service layer is acceptable. Keep it deterministic and test it thoroughly. If caches are used, key them by approved revision plus scenario/change-set hash so a working calculation can never overwrite an official cache entry.

### Files and lineage

Implement or adapt:

- `source_files`
- `source_file_versions`
- `import_runs`
- `import_issues`
- `exports`

Each uploaded file must have:

- Private storage key
- Original filename
- MIME/type classification
- SHA-256 checksum
- Byte size
- Uploaded by/at
- Source category
- Immutable version identity
- Supersedes relation when relevant
- Parse/validation status
- Import run
- Approval/change-request link
- Provenance notes

Never choose a production source by “newest workbook whose filename contains a keyword.” Resolve sources by registered type, explicit active version, checksum, and approved status.

### Jobs and events

Implement a Postgres-backed queue unless the repository already has a reliable queue:

- `jobs`: type, payload, status, priority, idempotency key, available time, lease owner/expiry, attempts, maximum attempts, last error, timestamps.
- `outbox_events`: transactionally records follow-up work produced by an approved write.

Claim jobs with a safe locking pattern such as `FOR UPDATE SKIP LOCKED`. Only one production worker is initially deployed. Jobs must be resumable and idempotent.

Required job types include or map to:

- File parse/validation
- Bhav validation
- Approved import application
- Affected-security analytics recalculation
- Portfolio recalculation
- Metrics-cache refresh
- Excel/CSV export generation
- Backup/health checks where appropriate

Replace the global “refresh everything” path with dependency-scoped jobs where safe. Retain a controlled full rebuild command for disaster recovery and verification.

### Operational storage policy

- Approved structured data: Postgres.
- Draft/submitted operations: Postgres.
- Original files and generated files: private object storage.
- File identity, lineage, approval, and checksum: Postgres.
- Browser localStorage: non-authoritative visual preferences only during transition, then remove business-state keys.
- OneDrive: optional human backup/mirror or migration intake, never production runtime storage.
- DailyEdit Excel: migration input and later generated export only, never live operational storage after cutover.

## 7. API contract

Adapt exact paths to existing routing conventions, but expose equivalent functionality.

### Change-request routes

- `POST /change-requests` — create a draft.
- `GET /change-requests` — authorized listing with filters.
- `GET /change-requests/{id}` — detail, operations, validation, impact and history.
- `PATCH /change-requests/{id}` — update an eligible draft.
- `POST /change-requests/{id}/submit` — validate and submit.
- `POST /change-requests/{id}/withdraw` — withdraw when allowed.
- `POST /change-requests/{id}/approve` — Samir-only business permission, conflict check, atomic application, audit and outbox creation.
- `POST /change-requests/{id}/reject` — Samir-only, reason required.
- `POST /change-requests/{id}/revise` — create a new draft from rejected/conflicted content without mutating history.
- `GET /change-requests/{id}/impact` — official vs proposed calculations.

All mutation routes require CSRF protection or an equivalent safe same-site design, permission checks, request IDs, idempotency where retryable, and structured error responses.

### Domain-edit behavior

Refactor existing UI mutation endpoints so they do not directly update approved tables for non-approvers.

- A Julesh/Yash edit adds or updates a typed operation in an active draft.
- The response returns the updated working row, derived working values, draft status, and request ID so the screen changes immediately.
- Samir’s edit creates the same evidence, displays a confirmation, and upon confirmation uses the same approval service to self-approve atomically.
- Never maintain a hidden direct-update path that bypasses the approval engine.

### View selection

Affected read APIs must accept a validated view selection, preferably a consistent query parameter or request header:

- `view=official`
- `view=mine`
- `view=proposal&change_request_id=...`

Default shared reports and exports to `official`. Default Julesh’s interactive edit screens to his last explicit choice, but make the mode unmistakable. Do not remember the mode in a way that could accidentally turn an official export into a working export.

Responses containing overlaid data must expose enough metadata for the UI to render:

- Approved value
- Working/proposed value
- Status
- Change-request ID
- Proposer
- Whether official calculations are affected yet

## 8. User-interface requirements

Use the existing design system. Do not redesign unrelated pages.

### Global view control

Add a clear, persistent control on affected screens:

- **Official**
- **My Working**

The active mode must be visually obvious and accessible. A working view must include a concise warning that its values are not official until approved.

### Julesh workflow

- Editing updates My Working view immediately.
- Changed rows/fields show Draft or Pending Approval badges.
- A compact tray/panel shows the active draft’s changed items.
- Julesh can add a reason/note.
- “Submit changes to Samir” validates and submits the entire change set.
- Julesh can see status, review note, rejection reason, conflicts, and history.
- Julesh can switch back to Official at any time.
- Rejected changes do not silently remain overlaid.

### Samir workflow

Add an approval inbox with:

- Pending count
- Proposer, date, domain, affected entities and reason
- Field-by-field before/after diff
- Validation issues and provenance
- Impact preview using the exact same calculation engine as My Working view
- Approve action with final confirmation
- Reject action with required reason
- Conflict state that cannot be overridden without creating/reviewing a new revision
- Audit/history link

Samir’s normal screens should default to Official view. Provide an explicit “Preview this proposal” action rather than silently overlaying proposals.

### Yash workflow

- Diagnostics and deployment information must not imply permission to approve business data.
- Yash can see technical import/job failures and submit corrections through the same workflow.

### Notifications

For the initial version, reliable polling or server-sent events are acceptable. Do not add architectural complexity solely for realtime branding.

- Samir should see a newly submitted request within approximately 15 seconds without a full page reload.
- Julesh should see approval/rejection within approximately 15 seconds.
- The user who makes an edit sees the local/API-confirmed working result immediately.

## 9. Domain migration requirements

Migrate domains in this order because later domains depend on earlier foundations.

### 9.1 Pivot and user/firm preferences

- Move selected firms, ordering, metadata, and authoritative selection state into Postgres.
- Remove `pivot-selected-firms` as a source of truth.
- Preserve ordering and `LIQUIDCASE` hiding.
- Decide explicitly which settings are firm-shared and which are personal.
- Firm-shared changes require Samir approval; purely personal visual settings may save directly to `user_preferences`.

### 9.2 Charts

Move into typed tables:

- Range high/low
- Weekly support/resistance
- Close overrides and their effective date/source
- Correction percentage settings, classified as personal or firm-wide
- Any required symbol mapping and as-of metadata

Preserve formulas and chart calculations. Stop writing operational values to `Charts*.xlsx`. Generate an Excel export on demand if users still need the workbook.

### 9.3 Client Portfolio

Move into explicit tables or existing normalized structures:

- Portfolio/book identity
- Security identity
- Approved quantity and effective date
- Index/date/portfolio flags with documented meaning
- Stock/full-market quantity if still a required business input
- MCap factor with provenance and effective date
- Benchmark yearly start/end values

Do not store derived Price, Value, Percent, Total, MCap or `%Firm` as manually editable facts unless an explicit override is part of the domain model. Compute them from approved inputs and the approved bhav as-of date.

My Working view must recompute these derived values from Julesh’s overlaid proposed inputs.

### 9.4 SCA LLP

Move:

- Quantity
- Blocked/Ramprasath quantity semantics
- Cash/bank balance
- Required price/revaluation inputs

Preserve current SCA calculations and produce export-only workbooks if necessary.

### 9.5 Bhav and market imports

- Store uploaded file in private staging.
- Register checksum and idempotency key.
- Parse into staging tables or a bounded staging representation.
- Validate format, series, dates, duplicates, conflicts and symbol identity.
- Generate an import change request with summary and issues.
- Let the proposer preview working valuations using the staged valid data without mutating approved price bars.
- Require Samir approval before applying the batch to approved `nse_bhav_bars`/price tables under the current strict business rule.
- Apply once, enqueue downstream recalculations, and record provenance.
- Re-uploading the same checksum must not duplicate rows or jobs.

Keep a documented future option for trusted automated market-data imports, but do not enable auto-approval in this implementation.

### 9.6 Research, masters and historical imports

- Upload immutable source versions to private storage.
- Preserve Research’s read-only/immutable meaning.
- Use explicit file categories and active approved versions.
- Parse into staging and generate validation/reconciliation output.
- Create approval requests for firm-data effects.
- Retain lineage from canonical rows and derived metrics back to file version/import run.
- Never overwrite or mutate an earlier source file version.

### 9.7 Watchlists, fundamentals and analytics

- Keep watchlists firm-shared.
- A shared membership or manual metric override change requires approval.
- Automated derived cache refreshes do not need separate human approval after their approved inputs exist, but must be deterministic, attributable to input versions, and rebuildable.
- Preserve missing-reason, provenance, quality and freshness diagnostics.

## 10. Data reconciliation before cutover

Create a deterministic reconciliation command/tool that accepts the two legacy Postgres exports and relevant DailyEdit/Research inputs without modifying them.

### Required authority rules

- Security identity: approved permanent Security Master wins; aliases remain recorded.
- Transactions, historical episodes and snapshots: authoritative Research transaction masters/snapshots plus existing reconciliation policy win after validation.
- Bhav: union by exchange/symbol/series/trading date, but conflicting values require a reported decision; do not pick by machine.
- Client/SCA positions, chart levels, cash and benchmark values: compare field by field and require explicit resolution for different non-null values.
- Watchlists: merge by canonical security identity, preserve provenance and ordering decisions.
- Pivot selection/order: report differences and require one approved firm ordering.
- Fundamentals: prefer validated snapshots with higher-quality provenance; never silently replace a sourced value with an unsourced one.
- Browser localStorage: import only explicitly identified business state once; ignore ephemeral UI state.

### Required reconciliation output

For every domain classify records as:

- Identical
- Only in Samir source
- Only in Julesh source
- Only in Research source
- Compatible merge
- Value conflict
- Identity conflict
- Invalid/unparseable
- Ignored by documented policy

Produce machine-readable JSON/CSV and a human-readable `DATA_RECONCILIATION_REPORT.md`. Include counts, keys, values, sources, timestamps/checksums, chosen resolution, decision owner and unresolved status.

The tool may generate a proposed migration bundle, but it must not import unresolved conflicts into approved production tables.

## 11. Deployment topology

Prepare a Railway-compatible deployment with three application services connected to one GitHub repository:

1. **UI** — Next.js public service.
2. **API** — FastAPI private/internal service where possible.
3. **Worker** — same backend image or codebase with a worker entrypoint, no public port.

Maintain `/backend` proxy behavior so the browser can use same-site HTTP-only cookies. Avoid cross-origin cookie complexity where possible.

Supabase provides:

- Production Postgres
- Direct connection for controlled migrations when required
- Pooled connection for autoscaling/runtime services
- Private object storage

Prepare placeholder-only environment documentation for variables equivalent to:

- `APP_ENV`
- `DATABASE_URL` for runtime/pooler
- `DATABASE_DIRECT_URL` for controlled migrations
- `SESSION_SECRET`
- `PUBLIC_APP_URL`
- `INTERNAL_API_URL`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY` backend only, if storage operations require it
- Storage bucket names
- Cookie/security configuration
- Worker identity/concurrency
- Feature flags for legacy Excel reads and approval workflow

Use actual existing variable names when available. Never expose backend secrets as `NEXT_PUBLIC_*` variables.

Production migrations must run as a single controlled release task, not concurrently on every API/worker startup.

## 12. Authentication and security hardening

Preserve the current login interface initially unless repository inspection shows Supabase Auth is already integrated or a migration is clearly safer. Centralization does not require rewriting authentication in the first release.

At minimum:

- Remove insecure seeded production passwords.
- Store strong password hashes using the project’s secure password library; prefer Argon2id if a migration is practical.
- Add forced password reset/provisioning flow.
- Use secure, HTTP-only, same-site cookies in production.
- Rotate the session secret at cutover.
- Add CSRF protection for cookie-authenticated state changes.
- Add login rate limiting and safe lockout/backoff.
- Enforce server-side authorization on every route; UI hiding is not security.
- Prevent contributor roles from accessing approval endpoints.
- Redact secrets and sensitive values from logs/audit JSON.
- Validate uploads by content, size, extension and parser limits.
- Protect against spreadsheet formula injection in generated CSV/Excel exports.
- Use parameterized ORM/SQL operations.
- Review CORS, trusted hosts, proxy headers and HTTPS assumptions.
- Run dependency, secret and static-security scans using existing repository tools or well-supported additions.

Document MFA as a required near-term production enhancement if it cannot be implemented safely within the existing auth stack in this program.

## 13. Backup, recovery and capacity

The initial Supabase Free database limit is 500 MB. Build capacity visibility before cutover:

- Admin diagnostic showing database size and largest tables/indexes.
- Warning at 350 MB.
- Critical alert at 450 MB.
- File-storage usage reporting.
- Growth notes for bhav, audit and fundamental tables.

Do not store source-file bytes in Postgres.

Because free-tier managed recovery may be insufficient, provide:

- An automated logical `pg_dump` workflow suitable for a scheduled job.
- Encryption before upload when the backup destination is not already appropriately encrypted/private.
- An independent backup destination separate from the operational database project.
- Retention configuration, initially 30 daily and 12 monthly copies where feasible.
- Checksum verification.
- A documented restore command into a fresh development database.
- A restore drill recorded in `ACCEPTANCE_REPORT.md` before production sign-off.

Do not claim backups work until a restore has actually been tested.

## 14. Testing requirements

Use the repository’s existing test frameworks and add missing layers. Tests must use fake users and fake credentials.

### Unit tests

- Role/permission checks.
- Change-request state transitions.
- Typed operation validation.
- Working overlay application.
- Official context exclusion of drafts/submissions.
- Row-version conflict detection.
- Atomic approval behavior.
- Rejection/withdrawal/revision behavior.
- Numeric precision.
- Audit redaction.
- Import checksum/idempotency.
- Job retry/lease behavior.

### Integration tests

- Julesh edit changes My Working response immediately but not Official response.
- Julesh submits; Samir can view exact diff and impact.
- Samir approves; Official updates for all users and working overlay resolves.
- Samir rejects; Official remains unchanged and Julesh sees the reason.
- Yash cannot approve through API even if the UI is manipulated.
- A stale proposal conflicts after an approved row changes.
- A multi-operation approval rolls back completely when any operation fails.
- Duplicate approval calls are idempotent.
- Duplicate file/import submission does not duplicate canonical rows.
- Official analytics/cache never use pending values.
- Derived Client Portfolio and SCA calculations match current validated behavior.
- Bhav commit triggers only affected downstream work.

### End-to-end tests

Use Playwright or the existing browser test stack with separate authenticated contexts for Samir, Julesh, and Yash:

1. Julesh edits a portfolio quantity.
2. Julesh sees changed quantity and derived working valuation.
3. Official view remains unchanged.
4. Samir receives the submitted request.
5. Samir previews full impact.
6. Samir approves.
7. All sessions show the new official value.
8. Audit history identifies proposer and approver.
9. Repeat with rejection.
10. Repeat with concurrent conflict.

Add corresponding E2E coverage for chart levels, pivot ordering, one watchlist operation, and a staged bhav import.

### Regression tests

- Existing transaction/episode reconstruction.
- Holdings.
- Client Portfolio valuation.
- MCap and `%Firm`.
- SCA quantity/cash/blocked quantity.
- Charts and overrides.
- Pivot order and hidden symbols.
- Watchlists and screener diagnostics.
- Authentication and session behavior.

## 15. Observability and operational controls

Add structured logs with request/change-request/import/job IDs. Do not log secrets or raw passwords.

Provide an admin health page or endpoints showing:

- API/database/storage connectivity
- Current approved data revision
- Pending change-request count
- Failed/leased/stuck job count
- Last successful bhav import
- Last successful backup/restore-drill date
- Database and storage size
- Migration version
- Application build/commit identifier

Add safe commands or admin actions to retry a failed idempotent job and to run a controlled full rebuild. Never expose destructive database actions through an ordinary UI button.

## 16. Phased execution

Complete these phases in order. Update `IMPLEMENTATION_STATUS.md` at each boundary. Commit locally after each completed phase using a clear conventional message. Do not push or deploy production without permission.

### Phase 0 — Repository audit and baseline

Deliver:

- As-is architecture and exact data paths.
- Inventory of tables, routes, Excel write paths, localStorage keys, caches, auth, Docker services and tests.
- Baseline test/build results.
- Credential exposure scan report without reproducing secrets.
- Identified dirty-worktree constraints.

Gate:

- Existing system can be built/tested or all pre-existing failures are recorded with evidence.

### Phase 1 — Architecture seams and feature flags

Deliver:

- Target architecture/decisions.
- Central database configuration supporting local, test and cloud URLs.
- Explicit runtime vs migration database connections.
- ReadContext abstraction.
- Feature flags for legacy Excel reads, legacy Excel writes, approval workflow and cloud storage.
- No production behavior change yet by default.

Gate:

- Existing behavior passes with flags off.

### Phase 2 — Schema and approval engine

Deliver:

- Migrations for roles/permissions, row versions, change requests, operations, audit, jobs/outbox and file lineage.
- Typed approval handler registry.
- State machine and authorization.
- Atomic approval/conflict/idempotency logic.
- Unit/integration tests.

Gate:

- Core approval tests pass, including no pending-to-official leakage.

### Phase 3 — Working/official APIs and UI

Deliver:

- View-aware API reads.
- Draft/submission/approval/rejection routes.
- Official/My Working UI.
- Julesh draft tray and status.
- Samir approval inbox, diff and impact preview.
- Polling/SSE notifications.
- Three-user E2E tests on a simple representative domain.

Gate:

- Quantity example works end-to-end with approve, reject and conflict.

### Phase 4 — Incremental jobs, storage and imports

Deliver:

- Private-storage adapter with local test implementation.
- Source/file-version/import tables and services.
- Postgres job worker and outbox processing.
- Staged validate-preview-approve-apply pipeline.
- Import idempotency and provenance.

Gate:

- Same file uploaded twice produces one canonical effect; unapproved import affects only authorized preview.

### Phase 5 — Domain migrations

Migrate Pivot/preferences, Charts, Client Portfolio, SCA, Bhav, Research sources, watchlists/manual overrides in the order specified above.

For each domain:

1. Add normalized storage and migration.
2. Add legacy reader/importer.
3. Generate side-by-side comparison.
4. Add working/official overlay.
5. Add approval handler.
6. Add tests.
7. Stop Excel/localStorage writes.
8. Add export if still needed.
9. Record acceptance evidence.

Gate:

- Every domain has zero unexplained regression differences on fixtures and no live Excel write path when the new flag is enabled.

### Phase 6 — Reconciliation tooling

Deliver:

- Read-only import of Samir/Julesh DB dumps and file trees.
- Deterministic authority rules.
- Machine and human conflict reports.
- Proposed migration bundle that excludes unresolved conflicts.
- Checksum manifest of all inputs.

Gate:

- Repeated runs on identical inputs produce identical output; no source input is modified.

### Phase 7 — Deployment preparation

Deliver:

- Railway service configuration/instructions for UI, API and worker.
- Supabase setup/migration/storage instructions.
- Placeholder `.env.example` updates.
- CI checks for backend tests, frontend tests/build, migrations, containers and security.
- Release migration command.
- Deployment, rollback and security runbooks.

Gate:

- Clean local production builds and a successful non-production cloud deployment when credentials are available.

### Phase 8 — Migration rehearsal

Deliver:

- Restore legacy dumps/copies into isolated rehearsal inputs.
- Reconciliation report.
- Staging import.
- Samir-approved test change sets using non-production accounts.
- Counts, totals and valuation comparison.
- Backup and restore drill.
- Performance and 500 MB capacity report.

Gate:

- Zero unexplained differences and successful restore.

### Phase 9 — Production cutover, only after explicit authorization

Runbook sequence:

1. Announce/freeze legacy writes.
2. Archive and checksum both local databases and DailyEdit/Research inputs.
3. Rotate exposed/default credentials and production secrets.
4. Run final reconciliation.
5. Resolve every blocking conflict with recorded owner/decision.
6. Apply schema migrations once.
7. Import approved canonical bundle.
8. Verify counts, balances, quantities, as-of dates, valuations and permissions.
9. Create/provision Samir, Julesh and Yash securely.
10. Run smoke and E2E approval tests.
11. Enable cloud/approval/domain feature flags.
12. Make legacy local systems read-only archives.
13. Provide one hosted URL.
14. Monitor jobs/logs closely during the agreed validation window.

Gate:

- Human sign-off by Samir and Yash against the definition of done.

### Phase 10 — Cleanup after stabilization

Only after sign-off:

- Remove production runtime dependency on Research/DailyEdit bind mounts.
- Remove obsolete Excel write code and business-state localStorage paths.
- Retain explicit migration/import/export utilities.
- Update Windows instructions so Julesh only needs a browser.
- Preserve archived legacy databases/files according to retention policy.
- Do not delete historical evidence.

Gate:

- All acceptance criteria pass with legacy runtime paths unavailable.

## 17. Definition of done

Do not call the project complete until every applicable item is evidenced in `ACCEPTANCE_REPORT.md`:

- Samir, Julesh and Yash use one hosted URL.
- They read from one production Postgres database.
- No user has a separate production database.
- Julesh immediately sees his own draft/submitted changes in My Working view.
- Julesh can always inspect Official view separately.
- Samir sees exact before/after and calculated impact before approval.
- Only Samir can approve firm-data changes.
- Yash’s technical role cannot bypass business approval.
- Official data changes only through an approved atomic change set.
- Every change records proposer, approver/rejector, timestamps, reason, before/after and request ID.
- Concurrent/stale proposals cannot silently overwrite approved data.
- Unapproved changes never affect official reports, analytics, caches, alerts or exports.
- Pivot, Charts, Client Portfolio, SCA, Bhav, Research imports and watchlists follow the new storage/approval model.
- No production feature writes DailyEdit Excel.
- No production feature depends on a user’s OneDrive mount.
- No business state exists only in browser localStorage.
- Bhav/import operations are centralized, idempotent and traceable.
- Heavy work runs through one resumable worker rather than three local stacks.
- Production schema is reproducible from migrations.
- Secrets are absent from source/browser bundles.
- Database capacity is monitored before 500 MB.
- Backups have been restored successfully in a test.
- Turning off all three laptops does not affect the application.
- Local legacy databases/files are archived and recoverable, not deleted.
- Documentation enables a new engineer to deploy, restore and operate the system.

## 18. Final Cursor response format

At the end of each Cursor run, respond with:

1. Current phase and status.
2. What was implemented, with exact files.
3. Tests/checks run and results.
4. Migrations created and whether they were applied only locally/test.
5. Security/data risks found without reproducing secrets.
6. Remaining blockers requiring a human, if any.
7. Exact next finite phase.
8. Git commits created; confirm nothing was pushed or deployed unless authorized.

Do not end with “continue iterating” or an unbounded recheck instruction. The next action must be one named phase or one explicit human task.

# END CURSOR MASTER PROMPT

---

## Expected implementation sequence at a glance

| Phase | Outcome |
|---|---|
| 0 | Repository/data-path audit and baseline |
| 1 | Cloud-ready seams, read contexts and feature flags |
| 2 | Approval schema, audit and concurrency engine |
| 3 | Julesh working view and Samir approval UI |
| 4 | Storage, staged imports and one worker |
| 5 | Pivot, Charts, Client, SCA, Bhav, Research and Watchlists migrated |
| 6 | Deterministic Samir/Julesh reconciliation tool |
| 7 | Supabase/Railway deployment configuration |
| 8 | Full migration rehearsal and restore test |
| 9 | Authorized production cutover |
| 10 | Removal of obsolete live Excel/local-machine paths |

## Human decisions deliberately reserved

Cursor should not guess these decisions:

- Supabase and Railway credentials/project identifiers.
- Authorization to deploy or migrate production.
- Resolution of conflicting Samir/Julesh business values.
- Production password/session-secret rotation timing.
- Production DNS/domain choice.
- Production cutover date and validation window.
- Whether trusted market-data imports may ever be auto-approved in the future.

