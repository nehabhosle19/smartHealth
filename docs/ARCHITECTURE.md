# Architecture

## Request flow
```
browser (ES modules, cookie session)
   │  fetch /api/...  (HttpOnly cookie + X-Requested-With)
   ▼
middleware.py   body limit · Host check · security headers
   ▼
routers/*       validate input (schemas.py) · authorise (deps.py) · stay thin
   ▼
service.py      6 bulk queries → DistrictState        routers/reports.py  upsert + audit log
   ▼
analytics.py    forecast · stock level · redistribution · risk score   (pure functions)
   ▼
presenters.py   translate (i18n.py) and shape JSON
```

## Design decisions
- **Pure analytics core.** `analytics.py` has no database or HTTP imports, so every rule
  (thresholds, donor reserve, scoring weights) is unit-tested with plain data. Tunables live in `config.py`.
- **Bulk loading, not N+1.** `service.compute_district` loads each table once for the whole scope and
  aggregates in Python; a dashboard costs a handful of queries regardless of the number of centres.
- **Explainable AI.** Holt damped-trend smoothing needs no training data and every flag carries the exact
  reasons and points, so an administrator can see *why* a centre was flagged.
- **Server-side translation.** Alerts are rendered in the requested language by the API (`i18n.py`), so
  every client sees identical wording; UI labels live in `static/i18n.js`.
- **Security by default.** No default accounts, HttpOnly SameSite cookies + CSRF header, per-facility
  authorisation in one dependency (`deps.facility_access`), strict bounded input models, fail-fast
  production config. Details in [SECURITY.md](../SECURITY.md).
- **No frontend build step.** Plain ES modules and canvas charts: nothing to compile, tiny payload, and
  the DOM is built with text nodes only (no `innerHTML`).

## Data model
`Facility` ─< `StockLog` (daily closing stock + consumption per medicine) ·
`Footfall` · `BedStatus` · `DoctorAttendance` · `TestAvailability` (latest audit per test) ·
`User` (role `admin` | `staff`, staff bound to one facility). Unique constraints make each daily report
an idempotent upsert.
