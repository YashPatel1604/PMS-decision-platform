# Dad laptop setup (Windows) — PMS Decision Platform

You run the app on **this PC**. Open it in a browser. You do **not** need Python or Node.

Software updates come from Yash (USA) via GitHub. Portfolio files come from **OneDrive Research**.

**Brand-new PC / first install?** Follow [`WINDOWS_NEW_PC_INSTALL.md`](./WINDOWS_NEW_PC_INSTALL.md) first (seeds, bhav, watchlist backfill, schedules). This doc is day-to-day use and troubleshooting after that.

---

## What you need installed (one time)

| Software | Why |
|----------|-----|
| OneDrive (same account as Yash) | Research Excel files |
| Docker Desktop for Windows | Runs the app |
| Git for Windows | Download / update the software |
| Tailscale | So Yash can help remotely when this PC is on |
| Chrome or Edge | Use the app |

---

## Step 1 — OneDrive Research

1. Sign into OneDrive with the **shared family account**.
2. Wait until the `Research` folder finishes downloading.
3. In File Explorer, open `Research`. You must see a folder named **`Portfolio`** inside it.
4. Right-click `Research` (or at least `Portfolio`) → **Always keep on this device**.
5. Click the address bar, copy the full path. Example shape:

```text
C:\Users\YourName\OneDrive\Some\Folders\Research
```

Keep this path for Step 4. The path must end at **`Research`**, not at `Portfolio`.

---

## Step 2 — Install Docker Desktop

1. Download: [https://www.docker.com/products/docker-desktop/](https://www.docker.com/products/docker-desktop/)
2. Install. Enable **WSL 2** if asked.
3. Restart Windows if prompted.
4. Start **Docker Desktop**. Wait until it says the engine is running (green / “Docker Desktop is running”).
5. Leave Docker Desktop running whenever you use the PMS app.

---

## Step 3 — Install Git and Tailscale

1. Git: [https://git-scm.com/download/win](https://git-scm.com/download/win) — default options are fine.
2. Tailscale: [https://tailscale.com/download/windows](https://tailscale.com/download/windows)
3. Sign into Tailscale with the invite Yash sent you. Status should show **Connected**.

---

## Step 4 — Download the software

Open **PowerShell**:

```powershell
New-Item -ItemType Directory -Force -Path "$HOME\Apps" | Out-Null
cd $HOME\Apps
git clone https://github.com/YashPatel1604/PMS-decision-platform.git
cd PMS-decision-platform
Copy-Item .env.example .env
notepad .env
```

In Notepad, set these lines (use **your** Research path; forward slashes are OK):

```env
POSTGRES_PASSWORD=choose-a-long-password
RESEARCH_DIR=C:/Users/YourName/OneDrive/Some/Folders/Research
NEXT_PUBLIC_API_URL=/backend
API_INTERNAL_URL=http://api:8000
```

(`NEXT_PUBLIC_API_URL=/backend` is required so login cookies work through the UI proxy. Do **not** use `http://127.0.0.1:8000` for the UI.)

Save and close Notepad.

If `git clone` asks for GitHub login: Yash must add your GitHub user as a collaborator on the private repo, or give you a personal access token.

---

## Step 5 — First start

Docker Desktop must be running. In PowerShell:

```powershell
cd $HOME\Apps\PMS-decision-platform
.\scripts\windows\start.ps1
```

Or manually:

```powershell
docker compose up -d --build
docker compose ps
```

First build can take **10–20 minutes** and needs internet. Later starts are much faster.

When `postgres`, `api`, and `ui` show as running / healthy:

1. Open Chrome: [http://localhost:3000](http://localhost:3000)
2. Optional check: [http://localhost:8000/docs](http://localhost:8000/docs)
3. Click **Refresh data** in the app. Wait until it finishes successfully.
   (Masters ship in `docker/final_master_seed`; Research supplies portfolio snapshots and History values.)
4. Open **Holdings** and confirm numbers look right.
5. Bookmark `http://localhost:3000`.

---

## Step 6 — Confirm market data and analysis populated

Refresh now includes:
- market-data import (prices, dividends, benchmarks, successors)
- episode analysis recompute

After Step 5, hard-refresh the browser (Ctrl+F5). Open positions and exit signals should show numbers instead of `—`.

If you still see blanks, run this manual fallback once:

```powershell
cd $HOME\Apps\PMS-decision-platform
.\scripts\windows\load-market-analysis.ps1
```

---

## Every day

1. Start **Docker Desktop** (if it is not already running). Containers are set to restart with Docker.
2. Open the bookmark `http://localhost:3000`.
3. If the page fails: wait 30 seconds for containers to wake, or run `.\scripts\windows\start.ps1` again.

**Watchlist alerts (daily scheduled task):** includes BSE insider store sync (last 14 days, portfolio + watchlist per-scrip backfill):

```powershell
cd $HOME\Apps\PMS-decision-platform
.\scripts\windows\refresh-watchlists.ps1 -SkipFundamentals
```

**Watchlist quotes (daily scheduled task):** valuation, promoter, price returns, and **materialized screener cache** — Dad’s screener opens instantly:

```powershell
.\scripts\windows\refresh-watchlist-quotes.ps1
```

**Screener.in export sync (daily 18:30 IST):** primary fill for ROCE/ROE/PE/CAGRs/etc.

1. On [screener.in](https://www.screener.in) open your watchlist/screen → **Edit columns** (add BSE Code, ROCE, ROE, Sales Qtr, …) → **Export**.
2. Save the file into the external data folder: `fundamentals/screener/`  
   (Docker: under `ONEDRIVE_EXTERNAL_DATA_DIR` / `EXTERNAL_DATA_DIR`).
3. At **18:30 IST** the job imports the newest CSV/XLSX, **BSE-fills** any watchlist codes still missing sales/mcap, refreshes returns from price history, rebuilds the screener cache.

```powershell
.\scripts\windows\sync-screener-export.ps1
# or: docker compose exec -T api uv run pms-platform sync-screener-export
```

**NSE bhav Final (IST):** tries **CM-UDiFF Common Bhavcopy Final** for **today only** at **17:00 IST**, retries at **17:15 IST**. Skips both pulls if that day is **already committed** (manual upload anytime, or a successful 17:00 run). No older-day auto-fill — if both auto tries miss and nothing was uploaded, Dad uploads the zip on **Pivot Point Strategy**.

```powershell
.\scripts\windows\sync-nse-bhav.ps1
```

Set the PC timezone to **India Standard Time** so Task Scheduler times match IST.

**Watchlist fundamentals (weekly scheduled job):** full BSE quarterly + annual + snapshot recompute (run overnight for ~200 stocks):

```powershell
.\scripts\windows\refresh-watchlist-fundamentals.ps1
```

Register scheduled tasks once (run this on Dad’s PC; it cannot be installed from another machine):

```powershell
.\scripts\windows\install-watchlist-schedule.ps1
```

That registers alerts (07:00 IST), quotes (07:15 IST), **Screener export sync (18:30 IST)**, **NSE bhav (17:00 + 17:15 IST)**, and weekly fundamentals.
**One-time Fair Value seed** (names from Research `Stocks_FairValue_Watchlist.xlsx`):

```powershell
docker compose exec api pms-platform seed-watchlist
```

If that watchlist already has members, add `--force` to fill in missing names.

Manual full refresh (fundamentals + quotes + alerts):

```powershell
.\scripts\windows\refresh-watchlists.ps1
```

Set `FUNDAMENTALS_PROVIDER=xbrl` in `.env` for live BSE quarterly results.

**Sleep:** if the laptop sleeps, the app pauses. Wake the PC and reopen the bookmark. While working, you can set Windows to not sleep.

---

## After Yash sends a software update

He will push to GitHub. On this PC:

```powershell
cd $HOME\Apps\PMS-decision-platform
.\scripts\windows\update.ps1
```

Then refresh the browser (Ctrl+F5).

If Open positions % or exit analysis still look empty after an update/reimport, also run:

```powershell
.\scripts\windows\load-market-analysis.ps1
```

---

## After portfolio Excel files change in OneDrive

1. Wait until OneDrive finishes syncing (no pending arrows on the files).
2. In the app, click **Refresh data**.
3. No `git pull` needed for data-only changes.
4. If you still see blank percentages, run `.\scripts\windows\load-market-analysis.ps1`.

---

## Troubleshooting

| Problem | What to try |
|---------|-------------|
| Portfolio value shows `src MODEL_PORTFOLIO` instead of `HISTORY` | See **Fix: History not used** below |
| `RESEARCH_DIR` error on start | Path in `.env` wrong; must contain `Portfolio` folder |
| Refresh: no portfolio snapshots | See **Fix: empty snapshots** below |
| Open positions all `—` / exit Insufficient Data | Refresh once more, then run `.\scripts\windows\load-market-analysis.ps1` as fallback |
| Refresh fails / empty data | Mark Research **Always keep on this device**; re-run Refresh |
| Page won’t load | Docker Desktop running? `docker compose ps` |
| `git clone` / `git pull` denied | Ask Yash for GitHub access |
| Disk full | Docker Desktop → Settings → Resources; free disk space |
| Old containers | `docker compose down` then `.\scripts\windows\start.ps1` |

### Fix: empty snapshots (`No portfolio snapshot workbooks…`)

Docker on Windows often cannot see OneDrive cloud-only files. Do all of these:

1. In File Explorer open your `Research\Portfolio` folder (and **`Portfolio Yearly`** if it exists).
2. Right-click → **Always keep on this device**. Wait until green checkmarks (not cloud icons).
3. Confirm `.env` `RESEARCH_DIR` ends at **`Research`** (the folder that contains `Portfolio`), e.g.  
   `RESEARCH_DIR=C:/Users/Dad/OneDrive/.../Research`
4. Pull the latest app (includes a snapshot seed fallback) and rebuild:

```powershell
cd $HOME\Apps\PMS-decision-platform
git pull
docker compose up -d --build
```

5. Click **Refresh data** again.

Check what the container sees (optional):

```powershell
docker compose exec api ls -la /data/research/Portfolio
docker compose exec api ls -la "/data/research/Portfolio/Portfolio Yearly"
docker compose exec api ls -la /data/snapshot_seed
```

### Fix: History not used (`src MODEL_PORTFOLIO`)

Portfolio totals should come from `Research\Portfolio\History\PMS_ClientPortfolio_*.xlsx`.
If Holdings shows `src MODEL_PORTFOLIO`, Docker is using yearly `Portfolio_*.xlsx` books
(often the snapshot seed) because **History is missing or unreadable** in the container.

#### A. Confirm History exists on the PC (not only in Research)

```powershell
# Show what .env points at
Get-Content .env | Select-String RESEARCH

# On the host — this path must work (use your RESEARCH_DIR value)
$dir = (Get-Content .env | Where-Object { $_ -match '^RESEARCH_DIR=' }) -replace '^RESEARCH_DIR=',''
dir "$dir\Portfolio"
dir "$dir\Portfolio\History"
```

- If `dir "$dir\Portfolio"` fails → `.env` `RESEARCH_DIR` is wrong. It must be the folder that
  **contains** `Portfolio` (named `Research`), not a random parent and not usually `History` itself.
- If Portfolio lists but History is missing → open OneDrive → pin `History` → **Always keep on this device**.

#### B. Confirm Docker sees the same tree

```powershell
docker compose exec api ls -la /data/research
docker compose exec api ls -la /data/research/Portfolio
docker compose exec api ls -la /data/research/Portfolio/History
curl http://127.0.0.1:8000/health/research
```

| What you see | Meaning |
| --- | --- |
| `/data/research` empty or wrong | Bad mount — fix `RESEARCH_DIR`, then recreate API |
| `/data/research/Portfolio` ok, no `History` | Host folder incomplete / OneDrive cloud-only |
| `History` works after recreate | Path was fine; container had stale mount |

Common mistake: setting `RESEARCH_DIR=…\Research\Portfolio`. Prefer `…\Research`.
(Newer builds accept Portfolio as well, but still recreate after changing `.env`.)

```powershell
cd $HOME\Apps\PMS-decision-platform
# Edit .env so RESEARCH_DIR=C:/Users/.../Research  (folder that contains Portfolio)
git pull
docker compose up -d --build --force-recreate api
```

Then hard-refresh the browser (Ctrl+F5). For 31 Dec 2025 you should see `src HISTORY`.

### Corporate actions (splits / bonuses)

- **Quantities** while you held a stock: already in the transactions master as `Split`/`Bonus` (matches History).
- **Price units** (first-buy / underwater / continuous-loss): use Yahoo calendar file shipped in the app seed:
  `docker/market_data_seed/corporate_actions/corporate_actions.csv`
- After Yash pushes an update: `git pull` → rebuild API → Refresh. Same CSV on both machines.

---

## Security notes

- Do not open ports 3000/8000 to the public internet.
- Do not commit or share your `.env` file.
- Tailscale is for family support only; keep it Connected when Yash needs to help.
