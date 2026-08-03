# Dad laptop setup (Windows) — PMS Decision Platform

You run the app on **this PC**. Open it in a browser. You do **not** need Python or Node.

Software updates come from Yash (USA) via GitHub. Portfolio files come from **OneDrive Research**.

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
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

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

## Every day

1. Start **Docker Desktop** (if it is not already running). Containers are set to restart with Docker.
2. Open the bookmark `http://localhost:3000`.
3. If the page fails: wait 30 seconds for containers to wake, or run `.\scripts\windows\start.ps1` again.

**Sleep:** if the laptop sleeps, the app pauses. Wake the PC and reopen the bookmark. While working, you can set Windows to not sleep.

---

## After Yash sends a software update

He will push to GitHub. On this PC:

```powershell
cd $HOME\Apps\PMS-decision-platform
.\scripts\windows\update.ps1
```

Then refresh the browser (Ctrl+F5).

---

## After portfolio Excel files change in OneDrive

1. Wait until OneDrive finishes syncing (no pending arrows on the files).
2. In the app, click **Refresh data**.
3. No `git pull` needed for data-only changes.

---

## Optional: market prices

After a successful Refresh, in PowerShell:

```powershell
cd $HOME\Apps\PMS-decision-platform
docker compose exec api uv run pms-platform import-market-data
```

This needs internet and can take a while.

---

## Troubleshooting

| Problem | What to try |
|---------|-------------|
| `RESEARCH_DIR` error on start | Path in `.env` wrong; must contain `Portfolio` folder |
| Refresh: no portfolio snapshots | See **Fix: empty snapshots** below |
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

---

## Security notes

- Do not open ports 3000/8000 to the public internet.
- Do not commit or share your `.env` file.
- Tailscale is for family support only; keep it Connected when Yash needs to help.
