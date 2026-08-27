# Migration Runbook (draft)

**Status:** Phase 6+ — not executable until reconciliation tooling exists.

## Preconditions

- [ ] Human authorization for production
- [ ] Samir/Julesh legacy DB dumps archived with checksums
- [ ] DailyEdit + Research trees archived
- [ ] All blocking conflicts resolved in `DATA_RECONCILIATION_REPORT.md`

## Sequence

1. Freeze legacy writes.
2. Run reconciliation tool (read-only on sources).
3. Resolve conflicts with recorded owner/decision.
4. Apply schema migrations once via `DATABASE_DIRECT_URL`.
5. Import approved canonical bundle.
6. Verify counts and sample valuations.
7. Enable feature flags per cutover checklist.

See master plan Phase 9 for full steps.
