# Force-reload prices from the repo seed (not a stale OneDrive external folder),
# then rebuild exit / ownership analysis.
# Requires Docker stack running.
$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

Write-Host "Checking repo market-data seed inside API container ..." -ForegroundColor Cyan
docker compose exec -T api ls -la /data/external_seed/prices/daily_prices.csv
if ($LASTEXITCODE -ne 0) {
    Write-Host "Missing seed CSV. Run git pull, then docker compose up -d --build api." -ForegroundColor Red
    exit 1
}

Write-Host "Clearing existing daily prices (so old EOD2 rows cannot win) ..." -ForegroundColor Cyan
docker compose exec -T api uv run python -c @"
from sqlalchemy import delete, func, select, text
from pms_platform.db import get_session_factory
from pms_platform.models import DailyPrice, ImportBatch

s = get_session_factory()()
# TRUNCATE avoids leftover rows that DELETE+reimport can race with.
s.execute(text('TRUNCATE TABLE daily_prices RESTART IDENTITY'))
batches = list(
    s.scalars(
        select(ImportBatch).where(
            ImportBatch.source_type.in_(['daily_prices', 'daily_prices_yahoo_repair'])
        )
    )
)
for batch in batches:
    batch.source_checksum = f'INVALIDATED-{batch.import_batch_id}'
s.commit()
remaining = s.scalar(select(func.count()).select_from(DailyPrice)) or 0
print(f'cleared daily prices; remaining={remaining}; invalidated {len(batches)} import batch checksum(s)')
if remaining:
    raise SystemExit('daily_prices not empty after truncate')
s.close()
"@
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Importing market data from /data/external_seed (repo seed) ..." -ForegroundColor Cyan
docker compose exec -T api uv run pms-platform import-market-data --external-dir /data/external_seed
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Verifying Yahoo repair rows (Heritage / MOSL / GPIL / Idea / ThomasCook / PEL) ..." -ForegroundColor Cyan
docker compose exec -T api uv run python -c @"
from collections import Counter
from sqlalchemy import func, select
from pms_platform.db import get_session_factory
from pms_platform.models import DailyPrice, Security
s = get_session_factory()()
names = {'Heritage','MOSL','GPIL','Idea','ThomasCook','PEL'}
secs = {x.security_id: x.portfolio_name for x in s.scalars(select(Security)).all() if x.portfolio_name in names}
ids = set(secs)
rows = s.scalars(select(DailyPrice).where(DailyPrice.security_id.in_(ids))).all()
by = Counter((secs[r.security_id], r.source) for r in rows)
print('total_prices', s.scalar(select(func.count()).select_from(DailyPrice)))
for key, n in sorted(by.items()):
    print(f'{key[0]} | {key[1]} | {n}')
need = [n for n in names if not any(k[0]==n and k[1]=='YAHOO_CHART_REPAIR' for k in by)]
if need:
    print('MISSING_YAHOO_REPAIR:', ','.join(sorted(need)))
    raise SystemExit(2)
print('yahoo_repair_ok')
s.close()
"@
if ($LASTEXITCODE -ne 0) {
    Write-Host "Seed import did not load YAHOO_CHART_REPAIR rows. Check git pull / seed file." -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host "Analyzing episodes (ownership + post-exit signals) ..." -ForegroundColor Cyan
docker compose exec -T api uv run pms-platform analyze-episodes
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Done. Hard-refresh the browser (Ctrl+F5). Check Heritage STOCK%." -ForegroundColor Green
Write-Host "Note: if .env has ONEDRIVE_EXTERNAL_DATA_DIR pointing at an old folder, UI Refresh may reintroduce stale prices. Comment that line out." -ForegroundColor Yellow
