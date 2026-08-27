# Rollback Runbook (draft)

1. Disable feature flags (`FEATURE_APPROVAL_WORKFLOW`, cloud flags).
2. Revert Railway deployment to previous known-good image tag.
3. Restore Postgres from last verified logical backup if schema/data migration failed.
4. Keep legacy local Docker archives read-only — do not delete.

Human authorization required for production rollback.
