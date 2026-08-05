# Corporate actions calendar

Canonical split/bonus events used to convert raw trade prices into
back-adjusted daily-price units (same series as `daily_prices.csv`).

## Source of truth

| Concern | Source |
| --- | --- |
| Share **quantity** after split/bonus | Transaction master `Split` / `Bonus` rows |
| Price **unit** adjustment | This CSV (`YAHOO_FINANCE` chart splits) |

Rebuild anytime (needs network):

```bash
uv run pms-platform build-corporate-actions
```

On Dad's PC after `git pull` + Docker rebuild, the seed is mounted at
`/data/external` (or `/data/external_seed`). Refresh / analyze-episodes then
uses the same calendar automatically.

## Columns

See `CORPORATE_ACTIONS_COLUMNS` in `market_data/contracts.py`.
`held_through=true` and `in_transaction_ledger=false` means a quantity row
is still missing from the transactions master.
