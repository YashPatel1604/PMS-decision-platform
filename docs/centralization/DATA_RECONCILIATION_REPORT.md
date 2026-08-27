# Data Reconciliation Report

Run the Phase 6 tool to generate this file:

```bash
uv run pms-platform reconcile-cutover \
  --samir-url "postgresql+psycopg://user:pass@host:5433/pms_samir" \
  --julesh-url "postgresql+psycopg://user:pass@host:5433/pms_julesh" \
  --output-dir ./data/reconciliation \
  --research-dir "/path/to/Research"
```

Outputs:

- `reconciliation.json` — machine-readable row classifications
- `DATA_RECONCILIATION_REPORT.md` — human summary (written into `--output-dir`)

Sources are read-only. Unresolved `value_conflict` rows must not be imported to production.
