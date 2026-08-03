# Software updates from the US (Dad hosts in Mumbai)

Dad’s Windows laptop runs the app with Docker. You develop on your Mac and ship code through the private GitHub repo:

`https://github.com/YashPatel1604/PMS-decision-platform`

Portfolio Excel stays on **OneDrive Research** on his PC. You do not push the database.

---

## One-time setup (you)

1. Finish Docker packaging on `main` (Compose: postgres + api + ui).
2. Confirm the GitHub repo is **private**.
3. Invite Dad’s GitHub account as a **read** collaborator (Settings → Collaborators), **or** create a fine-grained PAT with `contents:read` for clone/pull only.
4. Install [Tailscale](https://tailscale.com/download) on your Mac; invite Dad’s email.
5. Keep a note of his Research path pattern (nested under OneDrive) for support calls.
6. Send him [`WINDOWS_DAD_SETUP.md`](WINDOWS_DAD_SETUP.md) and walk Phase B–D once (or do it yourself over Tailscale + Quick Assist).

---

## Shipping a code update

### On your Mac

```bash
cd /path/to/pms-decision-platform
# ... make changes, test locally ...
git status
git add -A
git commit -m "Describe why the change exists."
git push origin main
```

Message Dad (WhatsApp): “Update ready — run update script” **or** connect via Tailscale and run it yourself.

### On his Windows PC (after code pull, if analysis columns are blank)

```powershell
cd $HOME\Apps\PMS-decision-platform
.\scripts\windows\update.ps1
.\scripts\windows\load-market-analysis.ps1
```

`load-market-analysis.ps1` imports price/benchmark CSVs and rebuilds exit assessments. **Refresh data alone does not do this.**

Equivalent:

```powershell
git pull
docker compose up -d --build
```

Hard-refresh the browser (Ctrl+F5).

---

## Remote help via Tailscale

1. His laptop must be **on**, awake, and Tailscale **Connected**.
2. Your Mac Tailscale Connected — ping his machine name or `100.x.x.x`.
3. Prefer **Windows Quick Assist** or RDP over Tailscale for GUI work.
4. Or open a remote shell if you have OpenSSH enabled on his Windows box; otherwise use Quick Assist and run PowerShell there.

You cannot update his app while the laptop is off or asleep.

---

## Data / Research updates (not git)

When Research Excel changes (either of you edits via OneDrive):

1. Wait for OneDrive sync on **his** PC (Always keep on device).
2. In his browser app → **Refresh data**.
3. Optional market data:

```powershell
docker compose exec api uv run pms-platform import-market-data
```

Avoid editing the same workbook on two PCs at once (OneDrive conflicts).

---

## Local dry-run on your Mac (before telling Dad)

```bash
cd pms-decision-platform
cp -n .env.example .env   # if needed
# Set RESEARCH_DIR to your Mac Research path in .env (required)
# Masters default to ./docker/final_master_seed (committed copies of 02_Final_Master)
docker compose up -d --build
open http://127.0.0.1:3000
# Click Refresh data; spot-check Holdings
```

When you change masters in `02_Final_Master`, copy them into `docker/final_master_seed/` and commit so Dad’s Refresh stays current.

Use a **different** Postgres volume / password if you still run the old host-side Postgres on `5433` for development — full Compose also binds `5433`. Stop the old stack first: `docker compose down` in any old project using that port, or change the host port mapping temporarily.

---

## Database backups (his laptop)

Occasionally:

```powershell
cd $HOME\Apps\PMS-decision-platform
docker compose exec -T postgres pg_dump -U pms pms | Out-File -Encoding utf8 backup-pms.sql
```

Copy `backup-pms.sql` into OneDrive (outside Research write rules if you treat Research as read-only for agents).

---

## Checklist before first Dad handoff

- [ ] `docker compose up -d --build` works on your Mac with Research mounted
- [ ] Refresh data succeeds
- [ ] `main` pushed to GitHub
- [ ] Dad has collaborator/PAT access
- [ ] Tailscale invite sent
- [ ] He completed [`WINDOWS_DAD_SETUP.md`](WINDOWS_DAD_SETUP.md) through first Refresh
- [ ] He has bookmark `http://localhost:3000`

---

## Lightsail?

Family model is **Dad’s laptop**. Cloud hosting is optional later; see [`LIGHTSAIL_DEPLOY.md`](LIGHTSAIL_DEPLOY.md).
