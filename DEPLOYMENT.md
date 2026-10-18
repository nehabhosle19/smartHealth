# Deployment guide

The app is one container (FastAPI + static frontend) plus PostgreSQL. It **must be served over
HTTPS**: session cookies are `Secure`, and production mode will not start otherwise.

## 0. Before you start
1. Generate the signing secret: `python -c "import secrets; print(secrets.token_hex(32))"`
2. Decide your hostname (e.g. `health.example.org`) — it goes in `SMARTHEALTH_ALLOWED_HOSTS`.
3. Never commit `.env`; it is git-ignored.

## Option A — any VPS with Docker (recommended for full control)
```bash
git clone <your-repo> && cd <repo>
cp .env.example .env && nano .env        # secret, DB password, allowed host
docker compose up -d --build              # app on 127.0.0.1:8000, Postgres in a volume
docker compose exec app python -m smarthealth.manage create-admin --username district.admin
```
Put a TLS reverse proxy in front. Minimal **Caddy** (automatic HTTPS):
```
health.example.org {
    reverse_proxy 127.0.0.1:8000
}
```
Set `FORWARDED_ALLOW_IPS` to the proxy's IP (`*` is acceptable only when the app port is not
reachable except through the proxy — compose binds it to 127.0.0.1 for that reason).

Migrations run automatically on every start (`alembic upgrade head`).

## Option B — Render / Railway / Fly.io (managed platforms)
1. Create a **PostgreSQL** database on the platform and copy its connection URL.
2. Create a **Web Service from this repo using the Dockerfile**.
3. Set environment variables:

   | Variable | Value |
   |---|---|
   | `SMARTHEALTH_ENV` | `production` |
   | `SMARTHEALTH_SECRET` | the generated 64-hex-char secret |
   | `DATABASE_URL` | the platform's Postgres URL (`postgres://…` is fine) |
   | `SMARTHEALTH_ALLOWED_HOSTS` | your platform/custom hostname, e.g. `smarthealth.onrender.com` |
   | `SMARTHEALTH_COOKIE_SECURE` | `true` |
   | `FORWARDED_ALLOW_IPS` | `*` (the platform proxy is the only way in) |

4. Health check path: `/api/health`.
5. Open the service **Shell** and create the first admin:
   `python -m smarthealth.manage create-admin --username district.admin`

## Demo / hackathon hosting without a shell (e.g. free Render)
Shell access is a paid feature on some hosts, so the container can set up the demo for you:

1. Set `SMARTHEALTH_ENV=development` (demo data is refused in production) and
   `SMARTHEALTH_DEMO_PASSWORD=<the password you want the demo accounts to use>`.
2. Save — the service redeploys and, on every start, the entrypoint runs `manage.py bootstrap-demo`:
   * empty database, or data older than a day -> the demo district is (re)created with fresh dates;
   * data is current -> only the demo accounts' password is synced to the variable.
3. Log in as `admin` / `staff1`…`staff8` with that password. **To change or recover the password,
   just edit the variable** and save; nothing else to run.

Real (non-demo) accounts are never touched by this. Do not use it for real data.

## Loading your real data
```bash
python -m smarthealth.manage add-facility --name "PHC Rampur" --type PHC --district Sitapur --lat 27.50 --lon 80.70
python -m smarthealth.manage add-medicine --name "Paracetamol 500mg" --unit tablets
python -m smarthealth.manage list-facilities                       # note the ids
python -m smarthealth.manage create-staff --username rampur.phc --facility-id 1
```
(Prefix with `docker compose exec app` when using Docker.) Passwords are prompted for; for scripts
set `SMARTHEALTH_PASSWORD`. Staff then report daily stock, footfall, beds, attendance and test
audits; forecasts become meaningful after ~14 days of stock history.

Other commands: `set-password` (also logs the user out everywhere), `deactivate` / `activate`.

## Operations
- **Health**: `GET /api/health` → `{"status":"ok"}` (503 if the database is unreachable).
- **Logs**: JSON-free plain logs on stdout. `smarthealth.audit` records logins (success, failure,
  throttled) and every data write with user and facility — ship these to your log system.
- **Backups**: back up the Postgres volume/database (`pg_dump`) daily; test restores.
- **Upgrades**: `git pull && docker compose up -d --build` (migrations apply automatically).
- **Secret rotation**: changing `SMARTHEALTH_SECRET` signs everyone out; do it if it ever leaks.
- **Scaling**: raise `WEB_CONCURRENCY` for more workers. Login throttling is per process, so add
  proxy rate limiting (e.g. nginx `limit_req` on `/api/auth/login`) when you scale out.
- **Timezone**: `SMARTHEALTH_TZ` (default `Asia/Kolkata`) decides what "today" means for reports.

## Pre-launch checklist
- [ ] HTTPS works and HTTP redirects to it
- [ ] `SMARTHEALTH_SECRET` and DB password are random and stored only in the platform's secret store
- [ ] `SMARTHEALTH_ALLOWED_HOSTS` set to the real hostname
- [ ] Admin created with a unique long password; no demo accounts exist
- [ ] Database backups scheduled and a restore tested
- [ ] Hindi/Tamil text reviewed by a native speaker
