# Agent Instructions

1. Read README.md before changing code.
2. Never modify files under data/raw.
3. Never modify the sibling OneDrive `Research/` folder unless the user explicitly asks; treat it as read-only authoritative portfolio data.
4. Before analytics or ingestion assumptions, search `Research/` (especially `Research/Portfolio`) and prefer it over `02_Final_Master` / `data/raw` duplicates.
5. Never guess missing financial values.
6. Preserve source lineage for every imported row.
7. Treat LiquidCase as liquid holdings, not an equity security.
8. Corporate actions change quantity but are not investment decisions.
9. Do not build frontend features before ingestion, validation, reconciliation, and episode tests pass.
10. Use deterministic code for financial calculations.
11. Add or update tests with every business-logic change.
12. Do not silently correct source data.
13. Keep imports idempotent.
14. Run formatting, linting, type checking, and tests before finishing.
15. Summarize files changed, assumptions made, and unresolved issues.
16. Stop and flag ambiguity when a change could alter historical holdings or returns.
17. Open `PMS-Decision-Platform.code-workspace` so Cursor indexes both the app and Research.
