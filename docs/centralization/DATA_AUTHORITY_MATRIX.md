# Data Authority Matrix

| Domain | Canonical source (target) | Current source | Samir/Julesh risk | Approval required |
|--------|---------------------------|----------------|-------------------|-------------------|
| Security identity | Security Master + aliases | Research / Final Master | Low (shared Research) | Yes for master edits |
| Transactions / episodes | Research txn master → Postgres | Per-PC Postgres after Refresh | **High** | Yes |
| Bhav OHLC | `nse_bhav_bars` (approved import) | Per-PC Postgres | **High** | Yes (batch) |
| Client positions | `client_positions` (planned) | DailyEdit Model sheet | **High** | Yes |
| Mcap factor | Postgres column | Excel formula text | Medium | Yes |
| Price/Value/Total | Derived from bhav × qty | Per-PC bhav + Excel | **High** | N/A (derived) |
| Charts H/L/C | `charts_levels` (planned) | DailyEdit Range | **High** | Yes |
| Pivot selection | `pivot_portfolio_symbols` | Per-PC Postgres + localStorage | **High** | Yes (firm-shared) |
| SCA qty/cash | `sca_positions` (planned) | DailyEdit Quantity | **High** | Yes |
| Watchlists | Postgres watchlist tables | Per-PC Postgres | **High** | Yes (membership) |
| Fundamentals cache | Postgres snapshots | Per-PC Postgres | Medium | No (derived from approved imports) |
| Research files | Immutable storage versions | OneDrive Research | Low if synced | Yes for firm effects |
| UI layout prefs | `user_preferences` (planned) | localStorage | Low | No |

## Reconciliation authority (Phase 6)

When sources disagree, precedence is documented in `MIGRATION_RUNBOOK.md` — never silent merge of conflicting financial values.
