# Data Authority Matrix

| Domain | Canonical source (target) | Current source | Samir/Julesh risk | Approval required |
|--------|---------------------------|----------------|-------------------|-------------------|
| Security identity | Security Master + aliases | Research / Final Master | Low (shared Research) | **No** — staged import applies directly (D12) |
| Transactions / episodes | Research txn master → Postgres | Per-PC Postgres after Refresh | **High** | **No** — staged import applies directly (D12) |
| Bhav OHLC | `nse_bhav_bars` | Per-PC Postgres | **High** | **No** — upload/validate/commit stays automatic |
| Client positions | `client_positions` (`book=client`) | DailyEdit Model sheet | **High** | Yes (qty) |
| SCA positions | `client_positions` (`book=sca`) | DailyEdit Quantity sheet | **High** | Yes (qty) |
| Mcap factor | `client_positions.mcap_factor` | Excel formula text | Medium | **No** — direct DB edit (D12) |
| Price/Value/Total | Derived from bhav × qty | Per-PC bhav + Excel | **High** | N/A (derived) |
| Charts H/L/C | `charts_range_rows` (cloud mode) | DailyEdit Range | Medium | **No** — strategy levels, not holdings |
| Pivot selection (daily filter checkboxes) | browser `localStorage` (`pivot-selected-firms`) | Per browser | Low | **No** — personal UI filter only |
| Pivot watchlist firms | `pivot_portfolio_symbols` | Per-PC Postgres | **High** | TBD (add/remove firms) |
| SCA qty/cash | `client_positions` + `client_book_settings` | DailyEdit Quantity | **High** | Yes (qty only); bank direct |
| Watchlists | Postgres watchlist tables | Per-PC Postgres | **High** | **No** — firm-shared direct writes (D12) |
| Fundamentals cache | Postgres snapshots | Per-PC Postgres | Medium | No (derived from approved imports) |
| Research files | Immutable storage versions | OneDrive Research | Low if synced | **No** — validate + direct apply (D12) |
| UI layout prefs | `user_preferences` (planned) | localStorage | Low | No |

## Reconciliation authority (Phase 6)

When sources disagree, precedence is documented in `MIGRATION_RUNBOOK.md` — never silent merge of conflicting financial values.
