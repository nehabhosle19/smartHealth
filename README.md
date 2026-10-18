# Smart Health – AI-driven PHC/CHC management

Real-time monitoring for a district's health centres: medicine stock, patient footfall, beds,
doctor attendance and diagnostic-test availability — with early stock-out warnings, demand
forecasts, redistribution recommendations and automatic flagging of under-resourced centres to
district administrators. UI and alerts in English, Hindi and Tamil; light and dark themes.

![CI](../../actions/workflows/ci.yml/badge.svg)

## Features
- **Stock monitoring & early warnings** – cover = stock ÷ forecast demand; *critical* < 3 days, *warning* < 7-day lead time, with a suggested reorder quantity.
- **Demand forecasts** – Holt damped-trend exponential smoothing over 28 days of consumption → 14-day forecast chart.
- **Redistribution** – per medicine, most-urgent shortages are matched to the *nearest* centres with surplus (> 30 days' cover); donors always keep 21 days.
- **Automatic flagging** – explainable 0-100 risk score (stock 35, attendance 25, beds 20, tests 15, footfall surge 10, stale data 10). ≥ 40 is flagged, ≥ 65 high severity. A banner appears when a centre newly becomes high severity.
- **Live dashboard** – auto-refreshes every 30 s; footfall trend, bed occupancy, attendance, missing tests per centre.
- **Roles** – district *admin* sees everything; centre *staff* see and report only their own centre.

## Quick start (development, 2 minutes)
```bash
pip install -r requirements-dev.txt
python -m smarthealth.manage seed-demo          # fake data; prints demo logins once
python -m uvicorn smarthealth.app:create_app --factory
# open http://127.0.0.1:8000  -> admin / staff1 … staff8
python -m pytest                                 # 68 tests
```
Set `SMARTHEALTH_DEMO_PASSWORD` before `seed-demo` to choose the demo password.

## Production
See **[DEPLOYMENT.md](DEPLOYMENT.md)** (Docker + PostgreSQL, Render/Railway/VPS) and **[SECURITY.md](SECURITY.md)**.
In short:
```bash
cp .env.example .env        # fill in SMARTHEALTH_SECRET, passwords, your hostname
docker compose up -d --build
docker compose exec app python -m smarthealth.manage create-admin --username district.admin
```
There are **no default accounts**. Production mode refuses to start without a strong secret and
`Secure` cookies, and refuses to load demo data.

## Project layout
```
smarthealth/analytics.py   pure forecasting / redistribution / scoring (unit-tested)
smarthealth/service.py     bulk-loads data (few queries, no N+1) and feeds analytics
smarthealth/app.py         FastAPI app: auth, RBAC, validation, audit log, security headers
smarthealth/manage.py      admin CLI (create admin/staff, facilities, medicines, passwords)
migrations/                Alembic migrations (run automatically by the Docker entrypoint)
static/                    dependency-free frontend (no build step)
tests/                     68 tests: analytics, security, API/RBAC/validation/i18n, CLI, config
```

## Configuration
All via environment variables — see [.env.example](.env.example). Analytics thresholds live in
[smarthealth/config.py](smarthealth/config.py).

## Adding a language
Add a block to `MESSAGES` in `smarthealth/i18n.py` (alerts) and to `static/i18n.js` (UI), then add the
language to `LANGS` in `static/app.js`. Have a native speaker review translations before go-live.

## Limitations
- The forecaster is statistical (no ML training data required) and works best with ≥ 14 days of history.
- Data entry is per-record through the UI; there is no CSV bulk import or e-mail/SMS alerting yet.
- Login throttling is per process – add proxy-level rate limiting when running several instances.
