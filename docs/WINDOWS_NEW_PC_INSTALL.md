# New Windows PC install — PMS Decision Platform

Cold-start checklist for **any new PC** (Dad laptop, replacement machine, second office PC).

You run the app in a browser. You do **not** need Python or Node on the host.

Software updates come from GitHub. Portfolio / Pivot / Research files come from **OneDrive Research**.

Ongoing day-to-day notes (troubleshooting, Refresh, History) live in [`WINDOWS_DAD_SETUP.md`](./WINDOWS_DAD_SETUP.md). This doc is the **first boot** path only.

---

## What a new PC does *not* get for free

A fresh Docker Postgres volume has **no**:

| Data | Symptom if missing |
|------|--------------------|
| Pivot firms + bhav history | Pivot Point Strategy empty |
| Committed NSE bhav days | Client Portfolio / Pivot stuck on old or blank as-of |
| Watchlist members + annual history | Watchlists blank / weak 5Y metrics |
| Scheduled tasks | Daily bhav / alerts never run |

Rebuild (`docker compose up -d --build`) keeps data **unless** someone runs `docker compose down -v` (that wipes the DB — then re-run the seed section below).

---

## Prerequisites (install once)

| Software | Why |
|----------|-----|
| OneDrive (same family account as Yash) | Research Excel files |
| Docker Desktop for Windows | Runs postgres + api + ui |
| Git for Windows | Clone / update code |
| Tailscale (optional but recommended) | Remote help when PC is on |
| Chrome or Edge | Use the app |

Set the Windows timezone to **India Standard Time (IST)** before installing scheduled tasks.

---

## Step 1 — OneDrive Research

1. Sign into OneDrive with the shared family account.
2. Wait until `Research` finishes downloading.
3. Confirm `Research` contains a folder named **`Portfolio`**.
4. Also keep available on this device:
   - `Research\Portfolio` (and `History` if present)
   - Pivot workbook under `Research` (`PivotPoints*.xlsx`)
5. Right-click `Research` (or at least those folders) → **Always keep on this device**.
6. Copy the full path to **`Research`** (not `Portfolio`). Example:

```text
C:\Users\YourName\OneDrive\Some\Folders\Research
```

Docker cannot read OneDrive **cloud-only** placeholders. Green checkmarks required.

---

## Step 2 — Docker Desktop

1. Install from [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/).
2. Enable **WSL 2** if asked; restart if prompted.
3. Start Docker Desktop and wait until the engine is running.
4. Leave it running whenever you use the app or scheduled jobs.

If `update.ps1` / `docker compose` fails with `dockerDesktopLinuxEngine` / pipe not found → Docker is not running. Start it and retry.

---

## Step 3 — Git (+ Tailscale)

1. Git: [git-scm.com/download/win](https://git-scm.com/download/win) — defaults are fine.
2. Tailscale: [tailscale.com/download/windows](https://tailscale.com/download/windows) — connect with the family invite.

---

## Step 4 — Clone and configure

Open **PowerShell**:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
New-Item -ItemType Directory -Force -Path "$HOME\Apps" | Out-Null
cd $HOME\Apps
git clone https://github.com/YashPatel1604/PMS-decision-platform.git
cd PMS-decision-platform
Copy-Item .env.example .env
notepad .env
```

Set at least:

```env
POSTGRES_PASSWORD=choose-a-long-password
RESEARCH_DIR=C:/Users/YourName/OneDrive/Some/Folders/Research
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
FUNDAMENTALS_PROVIDER=xbrl
```

Notes:

- `RESEARCH_DIR` must end at **`Research`** (folder that contains `Portfolio`).
- Forward slashes are OK on Windows.
- Do **not** commit or share `.env`.
- If `git clone` is denied: Yash must add the GitHub user as a collaborator (or provide a PAT).

---

## Step 5 — First start

Docker Desktop must be running:

```powershell
cd $HOME\Apps\PMS-decision-platform
.\scripts\windows\start.ps1
```

Or:

```powershell
docker compose up -d --build
docker compose ps
```

First build can take **10–20 minutes**. Expect `postgres`, `api`, and `ui` healthy/running.

Then:

1. Open [http://localhost:3000](http://localhost:3000)
2. Optional API docs: [http://localhost:8000/docs](http://localhost:8000/docs)
3. Click **Refresh data** in the app and wait for success
4. Check **Holdings** looks right
5. Bookmark `http://localhost:3000`

If Open positions / exit signals are blank after Refresh:

```powershell
.\scripts\windows\load-market-analysis.ps1
```

---

## Step 6 — One-time data seeds (required on a new PC)

Run these from `$HOME\Apps\PMS-decision-platform` with Docker up and internet available.

### 6a — Pivot Point Strategy (firms + workbook history)

```powershell
docker compose exec -T api uv run pms-platform seed-pivot-from-research
```

Needs `PivotPoints*.xlsx` under DailyEditFiles (`DAILY_EDIT_DIR`). Research is a fallback only.

### 6b — Latest NSE bhav (as-of dates for Pivot + Client Portfolio)

Pivot and Client Portfolio **prices / as-of dates** come from committed rows in Postgres (`nse_bhav_bars`), **not** from calendar “today” and **not** from the Client Portfolio Excel alone.

```powershell
# Weekday / when NSE Final is published:
.\scripts\windows\sync-nse-bhav.ps1

# Or a specific trade date (use this on weekends to backfill Friday):
.\scripts\windows\sync-nse-bhav.ps1 -Date YYYY-MM-DD
```

If download fails: on **Pivot Point Strategy**, upload the CM-UDiFF Common Bhavcopy **Final** zip for that day, then validate/commit.

The same commit also refreshes **DailyEditFiles** (writable, not Research):

- `Charts*.xlsx` → `BhavCopy_NSE_CM`
- `SCA_LLP*Stock*.xlsx` → `cmbhavcopy` plus Quantity/Stocks PRICE and VALUE
- Client Portfolio / Pivot **read** `PMS_ClientPortfolio*.xlsx` and `PivotPoints*.xlsx` from this folder (qty/names stay in Excel)

Set `DAILY_EDIT_DIR` in `.env` (Compose default `../DailyEditFiles`). `RESEARCH_DIR` is optional for a Client-only PC.

### 6c — Watchlists + deep annual history

```powershell
docker compose exec -T api uv run pms-platform seed-watchlist

docker compose exec -T api uv run pms-platform backfill-watchlist-data `
  --annual-history --alias-history `
  --skip-financials --skip-prices --skip-valuation --force
```

Annual backfill can take **~45–60 minutes**. Optional check:

```powershell
docker compose exec -T api uv run pms-platform audit-watchlist-data
```

Hard-refresh the browser (Ctrl+F5) when done.

---

## Step 7 — Scheduled tasks (once)

PC clock must be **IST**.

```powershell
cd $HOME\Apps\PMS-decision-platform
.\scripts\windows\install-watchlist-schedule.ps1
```

That registers roughly:

| Task | When (IST) |
|------|------------|
| Watchlist alerts | ~07:00 daily |
| Watchlist quotes / screener cache | ~07:15 daily |
| NSE bhav Final | ~17:00 + 17:15 daily (today only) |
| Screener export sync | ~18:30 daily |
| Watchlist fundamentals | weekly overnight |

Docker Desktop must be running when those fire. If the laptop sleeps through 17:00–17:15, Friday’s bhav will not appear until you pull that date manually (see below).

---

## After install — sanity checklist

| Screen | Expect |
|--------|--------|
| Holdings | Numbers; prefer `src HISTORY` when History files are present |
| Pivot Point Strategy | Firms listed; daily rows for recent trade dates |
| Client Portfolio | As-of = **latest committed bhav day** (not Saturday/Sunday calendar date) |
| Watchlists / Screener | Members + metrics from DB (no live NSE/BSE while browsing) |

---

## Later updates (not a new PC)

```powershell
cd $HOME\Apps\PMS-decision-platform
.\scripts\windows\update.ps1
```

Then Ctrl+F5. Do **not** re-seed unless the DB was wiped.

---

## Common failure modes on a new / rebuilt PC

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `dockerDesktopLinuxEngine` / pipe error | Docker not running | Start Docker Desktop; retry |
| UI build fails on `/app/public` | Old commit before fix | `git pull` then rebuild |
| Schedule script errors on `today` | Old broken script | `git pull` → re-run `install-watchlist-schedule.ps1` |
| Pivot empty | No seed / no bhav | Step 6a + 6b |
| Client Portfolio as-of stuck (e.g. Thu when Fri exists) | Missed Friday Final bhav | `.\scripts\windows\sync-nse-bhav.ps1 -Date YYYY-MM-DD` or manual upload |
| Weekend “Pull today” does nothing useful | No trading day today | Pull last weekday explicitly |
| Seed / Holdings fail; container can’t see Research | Wrong `RESEARCH_DIR` or cloud-only files | Fix `.env`, pin Always keep on this device, `docker compose up -d --force-recreate api` |
| Watchlists empty / weak 5Y | Skipped seed/backfill | Step 6c |
| Everything wiped after `down -v` | Volume deleted | Re-run Steps 5–7 |

---

## Diagnose mounts (optional)

```powershell
Get-Content .env | Select-String RESEARCH
docker compose exec api ls -la /data/research
docker compose exec api ls -la /data/research/Portfolio
curl http://127.0.0.1:8000/health/research
```

---

## Security

- Do not expose ports 3000/8000 to the public internet.
- Do not commit or share `.env`.
- Tailscale is for family support only.

---

## Related docs

- [`WINDOWS_DAD_SETUP.md`](./WINDOWS_DAD_SETUP.md) — daily use, Refresh, History, Screener export, corporate actions
- [`WATCHLIST_ROADMAP.md`](./WATCHLIST_ROADMAP.md) — watchlist product notes
