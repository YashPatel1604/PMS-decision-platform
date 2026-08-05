# PMS calendar-year returns

Extracted from Research `CAGR_PMS.xlsx` (From Start sheet).

Used for Holdings **PORT %** (contribution-neutral time-weighted link of calendar years).
Do **not** use raw AUM start→end for stock-vs-portfolio comparisons.

Rebuild from Research:

```bash
uv run python -c "from pathlib import Path; from pms_platform.analytics.portfolio_calendar_returns import extract_calendar_from_cagr_workbook, write_portfolio_calendar_csv, clear_portfolio_calendar_cache; rows=extract_calendar_from_cagr_workbook(Path('/Users/yash/Library/CloudStorage/OneDrive-Personal/Research/Portfolio/CAGR_PMS.xlsx')); write_portfolio_calendar_csv(Path('docker/market_data_seed/portfolio/pms_calendar_returns.csv'), rows); clear_portfolio_calendar_cache()"
```
