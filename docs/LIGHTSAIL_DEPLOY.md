# AWS Lightsail deploy guide — PMS Decision Platform

End-to-end runbook so **you** host the app and **your dad** only opens a browser.

**Current repo status (important):**  
`docker-compose.yml` today only runs **Postgres**. API and UI are not containerized yet.  
**Phase 0** (Docker packaging) must be done in Agent mode before Phases 6–9 work. Phases 1–5 (AWS account + Lightsail box) can be done anytime.

---

## What you are building

```text
Your Mac / OneDrive Research
        │  (occasional sync / Refresh)
        ▼
AWS Lightsail (Mumbai) — always on
  ├── Docker: postgres + api + ui
  └── Private access via Tailscale (recommended)
        │
        ▼
Dad's Windows laptop — browser only
```

**Target monthly cost:** roughly **₹1,500–2,500** (~$20–30) for a 4 GB Lightsail instance + snapshots + static IP.

---

## Phase map (do in order)

| Phase | What | Who | Blocking? |
|------:|------|-----|-----------|
| 0 | Dockerize API + UI + Compose | You + Agent | **Yes** — needed before app runs on Lightsail |
| 1 | Create AWS account + billing guards | You | No |
| 2 | Create Lightsail instance (Mumbai, 4 GB) | You | No |
| 3 | SSH in, install Docker | You | No |
| 4 | Secure the box (firewall + Tailscale) | You | Strongly recommended |
| 5 | Put code on the server | You | Needs Phase 0 images/Compose |
| 6 | Configure env + Research data | You | Yes |
| 7 | First boot: migrate, Refresh, smoke test | You | Yes |
| 8 | Give dad access | You + Dad | After 7 works |
| 9 | Ongoing: updates + data refresh | You | Ongoing |

Print this file or keep it open and tick each checkbox as you go.

---

## Phase 0 — Package the app for Docker (do in Cursor Agent mode)

Ask Agent:

> Dockerize PMS for Lightsail: Dockerfile for API, Dockerfile for UI, full `docker-compose.yml` (postgres + api + ui), production `.env.example`, and update this guide’s Phase 5–7 commands if paths change.

Until that lands, you can still complete Phases 1–4 (account + empty server).

**Acceptance for Phase 0:**

- [ ] `docker compose up -d` on your Mac starts postgres, api (`:8000`), ui (`:3000`)
- [ ] UI loads and talks to API
- [ ] Refresh-from-Research works with a mounted `RESEARCH_DIR`

---

## Phase 1 — Create an AWS account (step by step)

### 1.1 Open the signup page

1. On your Mac, open: [https://aws.amazon.com/](https://aws.amazon.com/)
2. Click **Create an AWS Account** (or **Sign in** if you already have one).

### 1.2 Root account details

1. Enter a **root email** you control (prefer a dedicated email, e.g. `you+aws@…`).
2. Choose an **AWS account name** (e.g. `PMS-Family`).
3. Verify email with the code AWS sends.

### 1.3 Root password

1. Set a **long unique password**.
2. Store it in a password manager.
3. You will later create an IAM user and avoid daily use of the root account.

### 1.4 Contact and payment

1. Choose account type: **Personal** is fine for family use.
2. Enter your name, phone, address (India is fine).
3. Add a **credit/debit card**. AWS may place a small temporary authorization.
4. Complete **phone verification** (voice or SMS).

### 1.5 Support plan

1. Select **Basic support — Free**.
2. Finish signup and wait until the console loads (can take a few minutes).

### 1.6 Sign in to the console

1. Go to [https://console.aws.amazon.com/](https://console.aws.amazon.com/)
2. Sign in as **Root user** with the email/password you just created.

### 1.7 Turn on MFA for root (do this now)

1. Click your account name (top right) → **Security credentials**.
2. Under **Multi-factor authentication (MFA)**, click **Assign MFA device**.
3. Choose **Authenticator app** (Google Authenticator / 1Password / Authy).
4. Scan QR, enter two codes, save backup codes offline.

- [ ] Root MFA enabled

### 1.8 Billing alarm (avoid surprise bills)

1. In the top search bar, type **Billing** → open **Billing and Cost Management**.
2. Confirm you are in the **payer account** and billing is active.
3. Open **Budgets** → **Create budget**.
4. Choose **Cost budget** → e.g. monthly limit **$40**.
5. Alert when actual cost **> 80%** and **> 100%** → email yourself.
6. Optional: **Billing preferences** → enable **Receive Free Tier Usage Alerts** and **Receive Billing Alerts** (may require CloudWatch alarm in us-east-1 once; follow the console prompts).

- [ ] Budget alert email set

### 1.9 Create an IAM admin user (stop using root daily)

1. Search **IAM** → **Users** → **Create user**.
2. Username: `yash-admin` (or your name).
3. Check **Provide user access to the AWS Management Console**.
4. Create user → attach policy **AdministratorAccess** (fine for a solo family account; tighten later if you want).
5. Save the console sign-in URL, username, and password.
6. Enable **MFA** on this IAM user too.
7. Sign out of root; sign in as the IAM user for all remaining steps.

- [ ] IAM user created + MFA
- [ ] Root only for break-glass

---

## Phase 2 — Create the Lightsail instance

### 2.1 Open Lightsail

1. While signed in as IAM user, search **Lightsail** or open:  
   [https://lightsail.aws.amazon.com/](https://lightsail.aws.amazon.com/)
2. First visit may ask to enable Lightsail — accept.

### 2.2 Choose region (India)

1. Top-right region picker → **Mumbai (ap-south-1)** if offered.  
   If Mumbai is unavailable in Lightsail for your account, use **Singapore (ap-southeast-1)** as backup (slightly higher latency).

### 2.3 Create instance

1. Click **Create instance**.
2. **Instance location:** Mumbai (or Singapore).
3. **Platform:** Linux/Unix.
4. **Blueprint:** **OS Only** → **Ubuntu 24.04 LTS** (or newest Ubuntu LTS shown).
5. **Networking:** leave dual-stack defaults unless you know you need IPv6-only.
6. **SSH key:**  
   - Click **Change SSH key pair** → **Create new**.  
   - Download the `.pem` file once.  
   - Store it at e.g. `~/.ssh/pms-lightsail-mumbai.pem`  
   - Lock permissions on your Mac:

```bash
chmod 400 ~/.ssh/pms-lightsail-mumbai.pem
```

7. **Optional: Automatic Snapshots** — enable daily snapshots (small extra cost; worth it).
8. **Choose instance plan:**  
   - Prefer **$20–24 USD / month · 4 GB RAM · 2 vCPUs** (Postgres + API + UI need RAM).  
   - Avoid 512 MB / 1 GB for this stack.
9. **Identify your instance:** name it `pms-decision-platform`.
10. Click **Create instance**. Wait until status is **Running**.

- [ ] Instance running in Mumbai/Singapore
- [ ] `.pem` saved and `chmod 400`

### 2.4 Attach a static IP

1. In Lightsail, open **Networking** (left) → **Static IPs** → **Create static IP**.
2. Attach it to `pms-decision-platform`.
3. Copy the **Static IP** into a note — this is your server address.

- [ ] Static IP attached: `________________`

### 2.5 Firewall (Lightsail networking)

Open the instance → **Networking** tab → **IPv4 firewall**.

**Recommended (Tailscale path — Phase 4):**

| Application | Protocol | Port | Notes |
|-------------|----------|------|--------|
| SSH | TCP | 22 | Restrict to your home IP if possible |
| *(no 80/443/3000/8000 public)* | | | App reached only via Tailscale |

**Alternate (public browser, less ideal):**

| Application | Protocol | Port |
|-------------|----------|------|
| SSH | TCP | 22 |
| HTTP | TCP | 80 |
| HTTPS | TCP | 443 |

**Never** open Postgres (`5432` / `5433`) to `0.0.0.0` / Anywhere.

- [ ] Firewall configured
- [ ] Postgres not public

---

## Phase 3 — First SSH login + install Docker

### 3.1 Connect from your Mac

```bash
ssh -i ~/.ssh/pms-lightsail-mumbai.pem ubuntu@YOUR_STATIC_IP
```

First connect: type `yes` to trust the host key.

If permission denied: confirm user is `ubuntu` (Ubuntu blueprint), key path, and Lightsail SSH key matches the instance.

- [ ] SSH works

### 3.2 Update the OS

```bash
sudo apt update && sudo apt upgrade -y
sudo reboot
```

Reconnect after ~60 seconds.

### 3.3 Install Docker Engine + Compose plugin

```bash
# Docker's official convenience script (OK for a single Lightsail box)
curl -fsSL https://get.docker.com | sudo sh

sudo usermod -aG docker ubuntu
# apply group without re-login:
newgrp docker

docker --version
docker compose version
```

- [ ] `docker` and `docker compose` work **without** sudo

### 3.4 Optional: fail2ban for SSH

```bash
sudo apt install -y fail2ban
sudo systemctl enable --now fail2ban
```

---

## Phase 4 — Private access with Tailscale (recommended)

Dad then never needs a public website. Both of you join a private mesh; only Tailscale peers reach the app.

### 4.1 Create a Tailscale account

1. Open [https://login.tailscale.com/start](https://login.tailscale.com/start)
2. Sign up with Google/Microsoft/GitHub (your account).
3. You will invite dad later.

### 4.2 Install Tailscale on Lightsail

On the server (SSH session):

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Copy the login URL it prints, open it on your Mac, approve the device. Name it `pms-lightsail`.

```bash
tailscale ip -4
```

Write down the `100.x.x.x` address: `________________`

- [ ] Lightsail on Tailscale

### 4.3 Install Tailscale on your Mac

1. Download Tailscale for macOS from [https://tailscale.com/download](https://tailscale.com/download)
2. Sign in with the **same** Tailscale account.
3. Confirm you can ping the server:

```bash
ping 100.x.x.x
```

### 4.4 Dad’s Windows laptop (do in Phase 8)

He installs Tailscale, you invite his email under **Users** in the Tailscale admin console, he signs in, then opens `http://100.x.x.x:3000`.

### 4.5 Keep Lightsail firewall tight

With Tailscale working, you can leave **only SSH (22)** open publicly (or restrict 22 to your home IP). Do **not** need public 3000/8000.

---

## Phase 5 — Put the application on the server

Complete **Phase 0** first.

### 5.1 Choose how code gets to Lightsail

**Option A — Private GitHub (best for updates)**

1. Push `pms-decision-platform` to a **private** GitHub repo (if not already).
2. On Lightsail:

```bash
sudo apt install -y git
mkdir -p ~/apps && cd ~/apps
git clone https://github.com/YOUR_ORG/pms-decision-platform.git
cd pms-decision-platform
```

Use a GitHub **fine-grained PAT** or deploy key (never put passwords in shell history carelessly).

**Option B — Copy from your Mac**

```bash
# on Mac, from repo parent
rsync -avz -e "ssh -i ~/.ssh/pms-lightsail-mumbai.pem" \
  --exclude '.venv' --exclude 'node_modules' --exclude '.git' \
  ./pms-decision-platform/ \
  ubuntu@YOUR_STATIC_IP:~/apps/pms-decision-platform/
```

- [ ] Code present at `~/apps/pms-decision-platform`

### 5.2 Create production env file

On the server:

```bash
cd ~/apps/pms-decision-platform
cp .env.example .env
nano .env
```

Set at least (exact keys may match Phase 0 templates):

```env
APP_ENV=production
POSTGRES_PASSWORD=GENERATE_A_LONG_RANDOM_PASSWORD
DATABASE_URL=postgresql+psycopg://pms:GENERATE_A_LONG_RANDOM_PASSWORD@postgres:5432/pms
RESEARCH_DIR=/data/research
RAW_DATA_DIR=/data/raw
# UI must call API on an address dad's browser can reach:
# With Tailscale, use the Lightsail Tailscale IP:
NEXT_PUBLIC_API_URL=http://100.x.x.x:8000
```

Generate a password:

```bash
openssl rand -base64 32
```

Use the **same** password in `POSTGRES_PASSWORD` and `DATABASE_URL`.

- [ ] Strong DB password set
- [ ] `NEXT_PUBLIC_API_URL` uses Tailscale IP (or your chosen hostname)

### 5.3 Build and start containers

Exact service names will match Phase 0 Compose. Typical:

```bash
cd ~/apps/pms-decision-platform
docker compose up -d --build
docker compose ps
docker compose logs -f --tail=100
```

Expected: `postgres`, `api`, `ui` **healthy/running**.

- [ ] All three services up

---

## Phase 6 — Research / OneDrive data on Lightsail

Lightsail **cannot** see your Mac OneDrive automatically.

### 6.1 What must exist on the server

Minimum for Refresh / portfolio truth:

```text
/data/research/Portfolio/
  ├── Portfolio Yearly/     (Portfolio_*.xlsx)
  ├── History/              (PMS_ClientPortfolio_*.xlsx / .xls)
  ├── Values.xlsx
  ├── SECURITY_MASTER_V1.xlsx   (or newest master name you use)
  └── transaction master workbook(s)
```

`RESEARCH_DIR` should point at the folder that **contains** `Portfolio` (i.e. `/data/research` if layout is `/data/research/Portfolio/...`).

### 6.2 One-time copy from your Mac (simplest)

On your Mac, with Research fully local (“Always keep on this device”):

```bash
# Adjust source path to YOUR Research folder (the one that contains Portfolio)
ssh -i ~/.ssh/pms-lightsail-mumbai.pem ubuntu@YOUR_STATIC_IP \
  'sudo mkdir -p /data/research && sudo chown ubuntu:ubuntu /data/research'

rsync -avz -e "ssh -i ~/.ssh/pms-lightsail-mumbai.pem" \
  --exclude '.DS_Store' \
  "/Users/yash/Library/CloudStorage/OneDrive-Personal/Research/Portfolio/" \
  ubuntu@YOUR_STATIC_IP:/data/research/Portfolio/
```

If your Compose mounts `/data/research` into the API container as `RESEARCH_DIR`, confirm the mount in `docker-compose.yml` after Phase 0.

### 6.3 Later updates (when portfolio files change)

Re-run the same `rsync`, then in the UI click **Refresh data**, or:

```bash
curl -X POST http://127.0.0.1:8000/imports/refresh-from-onedrive
```

(from the server, or via Tailscale to the API).

### 6.4 Market prices (optional but needed for peers/quotes)

After portfolio import, from API container / documented make target:

```bash
docker compose exec api uv run pms-platform import-market-data
```

(Exact command depends on Phase 0 image entrypoint.)

- [ ] `/data/research/Portfolio` populated
- [ ] Refresh succeeded once
- [ ] (Optional) market data imported

---

## Phase 7 — First boot checklist (smoke test)

On your Mac (on Tailscale):

1. Open UI: `http://100.x.x.x:3000`
2. Open API docs: `http://100.x.x.x:8000/docs`
3. Click **Refresh data** — wait until success (can take minutes).
4. Open **Holdings** — confirm portfolio MV looks right for a known date (e.g. 31 Dec 2025 ≈ Research total).
5. Spot-check one chart / peer compare.

If UI loads but API calls fail: `NEXT_PUBLIC_API_URL` is wrong (must be reachable **from dad’s browser**, not `localhost` inside Docker).

- [ ] UI loads
- [ ] API docs load
- [ ] Refresh OK
- [ ] Holdings numbers sane

### 7.1 Migrations

If Compose does not auto-migrate:

```bash
docker compose exec api uv run alembic upgrade head
```

---

## Phase 8 — Give dad access

### 8.1 Invite to Tailscale

1. Tailscale admin → **Users** → invite dad’s email.
2. On his Windows PC: install Tailscale → sign in with invited account.
3. Confirm he sees device `pms-lightsail`.

### 8.2 Bookmark

Send him:

```text
PMS app:  http://100.x.x.x:3000
```

(Use the Lightsail Tailscale IPv4 from Phase 4.)

### 8.3 What he does **not** need

- Docker, Python, Node, uv, pnpm  
- OneDrive Research on his PC (unless you later want him to upload files)  
- AWS console access  

### 8.4 What you tell him

1. Turn on Tailscale (system tray).  
2. Open the bookmark.  
3. If it fails: check Tailscale is Connected; ask you if the Lightsail instance is running.

- [ ] Dad can open Holdings

---

## Phase 9 — Operations (ongoing)

### 9.1 When you update Research files

1. `rsync` Portfolio → `/data/research/Portfolio`  
2. **Refresh data** in UI  
3. Optionally re-run market data import  

### 9.2 When you update application code

```bash
ssh -i ~/.ssh/pms-lightsail-mumbai.pem ubuntu@YOUR_STATIC_IP
cd ~/apps/pms-decision-platform
git pull   # or rsync from Mac
docker compose up -d --build
```

### 9.3 Backups

- Lightsail **automatic snapshots** of the whole instance  
- Plus optional DB dump:

```bash
docker compose exec -T postgres pg_dump -U pms pms | gzip > ~/backup-pms-$(date +%F).sql.gz
```

Copy dumps off-box occasionally (to your Mac / OneDrive).

### 9.4 Stop / start (save money temporarily)

Lightsail console → instance → **Stop** / **Start**.  
Static IP stays attached. Tailscale may need `sudo tailscale up` after long stops.

### 9.5 Monitoring cost

- AWS Budgets email (Phase 1)  
- Lightsail home shows instance estimate  

---

## Security checklist (do not skip)

- [ ] Root MFA + IAM MFA  
- [ ] Budget alert  
- [ ] Strong Postgres password (not `pms`)  
- [ ] Postgres port not open on Lightsail firewall  
- [ ] Prefer Tailscale; avoid public `:3000`/`:8000` if possible  
- [ ] `.pem` and `.env` never committed to Git  
- [ ] Private GitHub repo  
- [ ] Snapshots enabled  

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `Permission denied (publickey)` | Wrong key/user | Use `ubuntu` + correct `.pem` |
| UI loads, API errors | `NEXT_PUBLIC_API_URL=localhost` | Set to Tailscale IP of server |
| Refresh finds no Research | Empty `/data/research` or wrong `RESEARCH_DIR` | Fix mount/path; re-rsync |
| Cloud-only Excel / corrupt xlsx | Synced placeholders from OneDrive | On Mac: Always keep on device, re-rsync |
| OOM / containers restart | 1–2 GB instance | Resize to **4 GB** plan in Lightsail |
| Dad timeout | Tailscale off or instance stopped | Start Tailscale / Start instance |
| Huge AWS bill | Other AWS services left on | Check Cost Explorer; stay in Lightsail only |

---

## Decision log (fill in as you go)

| Item | Value |
|------|-------|
| AWS account email | |
| IAM username | |
| Region | Mumbai / Singapore |
| Instance name | `pms-decision-platform` |
| Static IP | |
| Tailscale IP | |
| GitHub repo | |
| Dad Tailscale email | |
| Phase 0 Docker done? | Yes / No |

---

## Suggested next message to Agent

When ready to implement packaging:

```text
Implement Phase 0 from docs/LIGHTSAIL_DEPLOY.md:
Dockerfiles for API and UI, production docker-compose (postgres+api+ui),
env examples for Lightsail/Tailscale, Research volume mount, and
align Phase 5–7 commands in the same doc with what you actually ship.
```

Then come back to this guide at **Phase 1** (or continue from wherever you left off) and tick boxes as you complete each step.
