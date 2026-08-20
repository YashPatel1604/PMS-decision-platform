# Oracle Always Free VM + auth — PMS Decision Platform

End-to-end plan so **you** host one shared backend on an **Oracle Cloud Always Free** VM, add **invite-only login**, and **2 firm employees** open the app in a browser (via Tailscale). Dad / colleague do not run Docker.

**Decisions locked**

| Topic | Choice |
|-------|--------|
| Host | Oracle Cloud **Always Free** (Ampere A1), prefer **Mumbai** |
| Access | **Tailscale** private mesh (no public UI/API) |
| Auth | Invite-only **email + password**; session cookie (or short JWT) |
| Watchlists | **Firm-shared** — both users see/edit the same lists |
| Portfolio / fundamentals / screener cache | **Firm-wide** (one DB, one refresh schedule) |
| Paid alt | [LIGHTSAIL_DEPLOY.md](./LIGHTSAIL_DEPLOY.md) if Oracle capacity is unavailable |

**Repo status (as of this plan)**

- [x] Docker Compose already runs **postgres + api + ui** (`docker-compose.yml`)
- [x] **Auth (Phase 0)** — invite-only users, session cookie, login UI, `create-user` CLI
- [ ] Oracle VM + Tailscale + cutover not done yet

Print this file and tick checkboxes as you go.

---

## What you are building

```text
Your Mac Research (OneDrive)
        │  occasional sync / Refresh to VM
        ▼
Oracle Always Free VM (Mumbai) — always on
  ├── Docker: postgres + api + ui
  ├── Auth: invite-only accounts (2 employees)
  ├── Cron: daily quotes + weekly fundamentals
  └── Tailscale only (no public :3000 / :8000)
        │
        ├── You (browser) ── login ──► same app / same DB
        └── Colleague (browser) ── login ──► same app / same DB
```

**Target cost:** **$0 / month** on Always Free (within Oracle free limits).  
Budget a few hours for signup + capacity retries; Mumbai Ampere shapes often show “out of capacity” — keep a Singapore fallback or Lightsail as Plan B.

---

## Phase map (do in order)

| Phase | What | Who | Blocking? |
|------:|------|-----|-----------|
| 0 | **Auth + firm-shared model** in the repo | You + Agent | **Yes** before exposing the VM |
| 1 | Oracle Cloud account + Always Free limits | You | No |
| 2 | Create Ampere VM (Mumbai preferred) | You | Capacity can block |
| 3 | SSH, Docker, firewall (OCI security list) | You | After VM exists |
| 4 | Tailscale on VM + Mac + Windows | You + users | Strongly recommended |
| 5 | Deploy code + env on VM | You | Needs Phase 0 merged |
| 6 | Research / data on the VM | You | Yes for Refresh |
| 7 | Migrate, create 2 users, smoke test | You | Yes |
| 8 | Cut over browsers; stop dual local DBs | You + users | After 7 |
| 9 | Cron on VM; ongoing updates | You | Ongoing |

Phases 1–4 can proceed while Agent builds Phase 0.

---

## Phase 0 — Auth system (Agent mode)

Ask Agent (when ready to implement):

> Implement invite-only auth for firm-shared use: `users` table (email, password hash, name, role, active), register-disabled signup, admin CLI to create invites/users, login + logout API, HTTP-only session cookie (or short-lived JWT), FastAPI `get_current_user` on all mutating/read routes except health + login, Next.js login page + redirect if unauthenticated. Watchlists stay firm-shared (no `owner_user_id` isolation). Add `AUTH_SECRET` / session settings to `.env.example` and Compose.

### Product rules

1. **No public self-signup.** Only you create accounts (CLI or one-shot admin endpoint protected by a bootstrap secret).
2. **Two accounts** initially (you + colleague). Roles: `admin` | `member` is enough (`admin` can create users).
3. **Firm-shared watchlists** — existing watchlist tables unchanged for ownership; auth only answers “is this person allowed to use the app?”
4. **Optional later:** per-user alert acknowledgements (`acknowledged_by_user_id`). Not required for v1.
5. **Local Docker** can keep auth off via `AUTH_DISABLED=1` for solo Mac work, or always require login with a local admin user — prefer **always on** so prod/local behavior matches.

### Suggested schema (v1)

```text
users
  id              uuid PK
  email           citext UNIQUE NOT NULL
  password_hash   text NOT NULL
  display_name    text
  role            text NOT NULL  -- admin | member
  is_active       bool NOT NULL DEFAULT true
  created_at      timestamptz
  last_login_at   timestamptz nullable
```

Sessions: server-side row **or** signed cookie (HMAC with `AUTH_SECRET`). Prefer **signed HTTP-only cookie** for 2 users (less surface).

### API surface (v1)

| Method | Path | Auth? | Notes |
|--------|------|-------|--------|
| POST | `/auth/login` | No | email + password → Set-Cookie |
| POST | `/auth/logout` | Yes | clear cookie |
| GET | `/auth/me` | Yes | current user |
| POST | `/auth/users` | Admin | create invite/user |
| * | all other app routes | Yes | 401 if missing/invalid |

CLI:

```bash
uv run pms-platform create-user --email a@firm.com --name "…" --role admin
```

### UI

- `/login` page (email + password)
- If `/auth/me` fails → redirect to `/login`
- Show display name in header; Logout button
- Cookie must work cross-origin on Tailscale: UI `http://100.x.x.x:3000` → API `http://100.x.x.x:8000` → set `SameSite=Lax` + CORS credentials + `NEXT_PUBLIC_API_URL` to Tailscale API URL

### Acceptance for Phase 0

- [x] Migration creates `users`
- [x] Cannot hit watchlists/API without cookie (when `AUTH_DISABLED=0`)
- [x] Login works; logout clears access
- [x] Second user sees **same** watchlists (firm-shared; no ownership isolation)
- [x] Tests cover login + protected route rejection
- [x] `.env.example` documents `AUTH_SECRET`, optional `AUTH_DISABLED`

---

## Phase 1 — Oracle Cloud account

### 1.1 Sign up

1. Open [https://www.oracle.com/cloud/free/](https://www.oracle.com/cloud/free/)
2. Create an account (home region: prefer **India West (Mumbai)** if offered; else **Singapore** / **Japan** as fallback).
3. Complete email + phone + payment method verification (card required for identity; Always Free should not bill if you stay in free shapes).
4. Sign in to [OCI Console](https://cloud.oracle.com/).

- [ ] Account active; home region noted: `________________`

### 1.2 Always Free shapes (Ampere A1)

Oracle Always Free includes **Ampere A1** flex:

- Up to **4 OCPUs** and **24 GB RAM** total across A1 VMs in the tenancy
- For this stack use **one VM**: **2 OCPU / 12 GB RAM** (comfortable for Postgres + API + UI + refresh jobs)
- Boot volume: **~50–100 GB** boot (Always Free disk limits apply — stay within your tenancy’s free block storage)

If Ampere is unavailable in your region, try:

1. Another availability domain in the same region  
2. Smaller shape first (1 OCPU / 6 GB), then scale up  
3. Singapore / other region  
4. Fall back to [LIGHTSAIL_DEPLOY.md](./LIGHTSAIL_DEPLOY.md)

### 1.3 Billing guards

1. OCI Console → **Billing & Cost Management** → set a **budget alert** (e.g. $5) so you notice if something leaves Always Free.
2. Do **not** create paid GPU / large AMD shapes by mistake.
3. Prefer **Always Free-eligible** checkboxes when creating compute.

- [ ] Budget / email alert set

---

## Phase 2 — Create the VM

### 2.1 Create Compute instance

1. OCI → **Compute** → **Instances** → **Create instance**.
2. **Name:** `pms-decision-platform`.
3. **Placement:** Mumbai (or your home region) — try AD-1 / AD-2 / AD-3 if capacity fails.
4. **Image:** Canonical **Ubuntu 24.04** (or newest Ubuntu LTS).
5. **Shape:** **Ampere** → **VM.Standard.A1.Flex** → **2 OCPU / 12 GB**.
6. **Networking:** create or use default VCN; assign a **public IP** (needed for initial SSH + Tailscale bootstrap). You can remove public exposure of app ports later.
7. **SSH keys:** paste your Mac public key (`~/.ssh/id_ed25519.pub` or generate a dedicated key).
8. Create instance. Wait until **Running**.

If create fails with capacity: retry different AD / time of day / slightly smaller OCPU, or change region.

- [ ] Instance running  
- [ ] Public IP noted: `________________`  
- [ ] Private IP noted: `________________`

### 2.2 OCI firewall (Security List / NSG)

On the subnet security list (or NSG attached to the VNIC):

**Recommended (Tailscale path):**

| Direction | Protocol | Port | Source | Notes |
|-----------|----------|------|--------|--------|
| Ingress | TCP | 22 | Your home IP `/32` (or temporary `0.0.0.0/0`) | SSH |
| Ingress | UDP | 41641 | `0.0.0.0/0` | Tailscale (if direct; often works via DERP without this) |
| *(no 3000 / 8000 / 5432 from internet)* | | | | App via Tailscale only |

**Never** open Postgres to the public internet.

- [ ] Security list tightened  
- [ ] Postgres not public

### 2.3 Optional: reserved public IP

Attach a reserved public IP if you want a stable SSH address (still do not publish the UI).

---

## Phase 3 — First SSH + Docker

### 3.1 Connect from Mac

Ubuntu images on OCI often use user `ubuntu`:

```bash
ssh -i ~/.ssh/YOUR_KEY ubuntu@ORACLE_PUBLIC_IP
```

- [ ] SSH works

### 3.2 Update OS + install Docker

```bash
sudo apt update && sudo apt upgrade -y
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
newgrp docker
docker --version
docker compose version
```

Optional:

```bash
sudo apt install -y fail2ban git
sudo systemctl enable --now fail2ban
```

- [ ] Docker works without sudo

### 3.3 Note architecture

Ampere is **ARM64**. Your existing Dockerfiles must build on ARM (most Python/Node images do). If a dependency is x86-only, fix in Phase 5 or use a different free shape — prefer fixing ARM.

---

## Phase 4 — Tailscale (private access)

### 4.1 Tailscale account

1. [https://login.tailscale.com/start](https://login.tailscale.com/start)
2. Sign up; you will invite the second employee later.

### 4.2 Install on the Oracle VM

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Approve in browser; name device `pms-oracle`.

```bash
tailscale ip -4
```

Write down: `________________` (e.g. `100.x.x.x`)

- [ ] VM on Tailscale

### 4.3 Install on Mac + Windows

1. Install Tailscale on your Mac; same account; `ping 100.x.x.x`.
2. Invite colleague email in Tailscale admin → **Users**.
3. They install Tailscale on Windows and sign in.
4. Browser URL later: `http://100.x.x.x:3000` (after deploy).

### 4.4 Keep OCI ingress tight

After Tailscale works, restrict SSH to your IP if possible. Do **not** open 3000/8000 publicly — auth is necessary but not a substitute for network exposure control.

---

## Phase 5 — Deploy the app on the VM

Requires **Phase 0 auth** merged to the branch you deploy.

### 5.1 Get code onto the VM

**Preferred — private GitHub clone:**

```bash
mkdir -p ~/apps && cd ~/apps
git clone https://github.com/YashPatel1604/PMS-decision-platform.git
cd PMS-decision-platform/pms-decision-platform   # adjust if repo root differs
```

Use a deploy key or fine-grained PAT.

### 5.2 Production `.env` on the VM

```bash
cp .env.example .env
nano .env
```

Minimum:

```env
APP_ENV=production
POSTGRES_PASSWORD=<openssl rand -base64 32>
AUTH_SECRET=<openssl rand -base64 48>
# AUTH_DISABLED must be unset or 0 in production
FUNDAMENTALS_PROVIDER=xbrl

# Browser on Tailscale must reach API at the VM Tailscale IP:
NEXT_PUBLIC_API_URL=http://100.x.x.x:8000

# Research path *inside* the host, mounted into the API container:
RESEARCH_DIR=/home/ubuntu/research
```

Compose already maps host `RESEARCH_DIR` → `/data/research` in the API container.

Rebuild UI after changing `NEXT_PUBLIC_API_URL` (build-arg):

```bash
docker compose up -d --build
```

- [ ] Strong `POSTGRES_PASSWORD` + `AUTH_SECRET`  
- [ ] `NEXT_PUBLIC_API_URL` = Tailscale IP `:8000`

### 5.3 Bind ports carefully

Compose currently publishes `3000` and `8000` on `0.0.0.0`. On a public cloud IP that is risky even with auth.

**Hardening (do one):**

1. Change Compose publish to Tailscale IP only, e.g. `100.x.x.x:3000:3000`, **or**
2. Host firewall (`ufw`) allow 3000/8000 only from Tailscale CGNAT `100.64.0.0/10`, **or**
3. Serve via a Tailscale-only reverse proxy later

- [ ] UI/API not open to the whole internet

### 5.4 Start stack

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f --tail=80 api
```

- [ ] postgres + api + ui running

---

## Phase 6 — Research data on the VM

The VM does **not** see Mac OneDrive automatically.

### 6.1 Minimum tree

Host path (example) `/home/ubuntu/research/` should contain what Refresh needs, typically:

```text
research/
  Portfolio/
    … portfolio workbooks …
```

Prefer copying from the authoritative Research tree on your Mac (see workspace rule: Research is source of truth). Do **not** invent duplicate masters in-repo.

### 6.2 Sync options

| Method | When |
|--------|------|
| `rsync` / `scp` from Mac over SSH or Tailscale | Occasional full sync |
| Manual upload of changed workbooks | Small updates |
| Later: rclone to Object Storage | If sync becomes frequent |

Example from Mac (Tailscale IP):

```bash
rsync -avz --progress \
  "/Users/yash/Library/CloudStorage/OneDrive-Personal/Research/" \
  ubuntu@100.x.x.x:~/research/
```

Then run in-app **Refresh** (or CLI) against the mounted path.

- [ ] `Portfolio/` present on VM  
- [ ] Refresh succeeds once

---

## Phase 7 — First boot: migrate, users, smoke test

```bash
docker compose exec -T api uv run alembic upgrade head
docker compose exec -T api uv run pms-platform create-user \
  --email you@example.com --name "Yash" --role admin
docker compose exec -T api uv run pms-platform create-user \
  --email colleague@example.com --name "…" --role member
```

(Exact CLI name may match Phase 0 implementation.)

### Smoke checklist

From a Tailscale-connected browser:

1. Open `http://100.x.x.x:3000` → redirected to **login**
2. Wrong password → rejected
3. Correct login → watchlists / holdings load
4. Second user login → **same** firm watchlists
5. Logout → cannot call API
6. Optional: trigger weekly fundamentals once; screener stays fast (cache path)

- [ ] Auth gate works  
- [ ] Both users see shared data  
- [ ] Refresh / screener OK

---

## Phase 8 — Cut over (stop dual databases)

Today each PC has its **own** Postgres. After the VM is healthy:

1. Point both browsers at `http://VM_TAILSCALE_IP:3000` (bookmark).
2. **Do not** treat local Docker DB as source of truth anymore.
3. Optional: keep local Docker for offline/dev with `AUTH_DISABLED` or a local admin — never sync blindly both ways.
4. Export any watchlists only existing on Dad’s PC (`/watchlists/{id}/export`) and import once on the VM if needed.
5. Uninstall or disable Windows Task Scheduler refresh on Dad’s laptop (jobs move to VM — Phase 9).

- [ ] Both people use VM URL only  
- [ ] Local refresh schedules disabled on laptops

---

## Phase 9 — Cron on the VM (one schedule for everyone)

On the Oracle host (crontab or systemd timers), run against Compose:

**Daily quotes** (example 07:15 IST):

```bash
docker compose -f ~/apps/.../docker-compose.yml exec -T api \
  uv run pms-platform refresh-watchlist-quotes
```

**Daily insider store** (example 07:10 IST — keeps portfolio/watchlist filings complete):

```bash
docker compose -f ~/apps/.../docker-compose.yml exec -T api \
  uv run pms-platform sync-insider-disclosures --days 14
```

**Weekly fundamentals** (example Sunday 03:00 IST):

```bash
docker compose -f ~/apps/.../docker-compose.yml exec -T api \
  uv run pms-platform refresh-watchlist-fundamentals
```

Align with existing Windows scripts in `scripts/windows/` but **host them once on the VM**.

- [ ] Daily quotes cron  
- [ ] Daily insider sync cron (`sync-insider-disclosures --days 14`)  
- [ ] Weekly fundamentals cron  
- [ ] Laptop Task Scheduler jobs removed / disabled

### Updates

```bash
cd ~/apps/.../pms-decision-platform
git pull
docker compose up -d --build
docker compose exec -T api uv run alembic upgrade head
```

---

## Security checklist (ship bar)

- [ ] Tailscale required; UI/API not world-open  
- [ ] Strong `POSTGRES_PASSWORD` + `AUTH_SECRET`  
- [ ] Invite-only users (2 accounts)  
- [ ] HTTPS optional later (Tailscale Serve / Caddy) — nice-to-have for cookie hygiene  
- [ ] SSH key only; fail2ban optional  
- [ ] Oracle budget alert so paid shapes cannot surprise you  
- [ ] No Postgres port on public IP  

---

## Rollback / Plan B

| Problem | Action |
|---------|--------|
| Ampere capacity exhausted in Mumbai | Retry AD / other region / Lightsail guide |
| ARM build fails | Fix Dockerfile base images for `linux/arm64` |
| Auth blocks local solo work | Temporary `AUTH_DISABLED=1` only on laptop Compose |
| VM wiped | Restore from OCI boot volume backup + re-`rsync` Research; recreate users |

---

## Suggested Agent implementation order (Phase 0)

1. Migration + `User` model + password hashing (argon2/bcrypt)  
2. Auth routes + dependency + CORS credentials  
3. `create-user` CLI  
4. Next.js login + `credentials: "include"` on API client  
5. Compose / `.env.example` for `AUTH_SECRET`  
6. Tests  

Then you execute Phases 1–9 on Oracle.

---

## One-line summary

**One free Oracle VM + Tailscale + invite-only login + firm-shared watchlists** → both employees use the same live system; laptops become browsers only.
