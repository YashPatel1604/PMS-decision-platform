# Agent Instructions

1. Read README.md before changing code.
2. Never modify files under data/raw.
3. Never guess missing financial values.
4. Preserve source lineage for every imported row.
5. Treat LiquidCase as liquid holdings, not an equity security.
6. Corporate actions change quantity but are not investment decisions.
7. Do not build frontend features before ingestion, validation, reconciliation, and episode tests pass.
8. Use deterministic code for financial calculations.
9. Add or update tests with every business-logic change.
10. Do not silently correct source data.
11. Keep imports idempotent.
12. Run formatting, linting, type checking, and tests before finishing.
13. Summarize files changed, assumptions made, and unresolved issues.
14. Stop and flag ambiguity when a change could alter historical holdings or returns.
