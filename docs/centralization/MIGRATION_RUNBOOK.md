# Migration Runbook

**Status:** Phase 8 — bundle import + verify CLIs available; see [`REHEARSAL_RUNBOOK.md`](REHEARSAL_RUNBOOK.md).

## Reconciliation command

```bash
uv run pms-platform reconcile-cutover \
  --samir-url "$SAMIR_DATABASE_URL" \
  --julesh-url "$JULESH_DATABASE_URL" \
  --output-dir ./data/reconciliation
```

Review `data/reconciliation/DATA_RECONCILIATION_REPORT.md` and resolve all value conflicts before step 5.

- [ ] Human authorization for production
- [ ] Samir/Julesh legacy DB dumps archived with checksums
- [ ] DailyEdit + Research trees archived
- [ ] All blocking conflicts resolved in `DATA_RECONCILIATION_REPORT.md`

## Sequence

1. Freeze legacy writes.
2. Run reconciliation tool (read-only on sources).
3. Resolve conflicts with recorded owner/decision.
4. Apply schema migrations once via `DATABASE_DIRECT_URL`.
5. Import approved canonical bundle:

```bash
uv run pms-platform import-migration-bundle \
  --bundle ./data/reconciliation/migration_bundle.json \
  --bhav-source-url "$SAMIR_DATABASE_URL"
```

6. Verify counts and sample valuations:

```bash
uv run pms-platform verify-rehearsal --bundle ./data/reconciliation/migration_bundle.json
```

7. Enable feature flags per cutover checklist.

See master plan Phase 9 for full steps.
