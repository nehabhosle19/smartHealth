"""FastAPI application factory and HTTP API."""
from __future__ import annotations

import functools
import logging
from datetime import date, timedelta
from pathlib import Path
from collections.abc import Callable

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import analytics, config, schemas
from .db import make_engine, make_session_factory
from .i18n import resolve_lang, t
from .models import (
    Base, BedStatus, DoctorAttendance, Facility, Footfall, Medicine, StockLog,
    TestAvailability, User,
)
from .security import LoginThrottle, create_token, decode_token, hash_password, verify_password
from .service import compute_district

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
COOKIE_NAME = "sh_session"
CSRF_HEADER, CSRF_VALUE = "X-Requested-With", "smarthealth"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
MAX_BACKDATE_DAYS = 400

log = logging.getLogger("smarthealth")
audit = logging.getLogger("smarthealth.audit")


@functools.cache
def _dummy_hash() -> str:
    """Hash verified for unknown usernames so login timing doesn't reveal which exist."""
    return hash_password("dummy-password", config.PBKDF2_ITERATIONS)


SECURITY_HEADERS = {
    "Content-Security-Policy": ("default-src 'self'; img-src 'self' data:; base-uri 'none'; "
                                "form-action 'self'; frame-ancestors 'none'"),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
}


# --------------------------------------------------------------------------- dependencies
def get_db(request: Request):
    with request.app.state.session_factory() as session:
        yield session


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    auth = request.headers.get("Authorization", "")
    token, via_cookie = (auth[7:], False) if auth.startswith("Bearer ") else (
        request.cookies.get(COOKIE_NAME), True)
    if via_cookie and request.method not in SAFE_METHODS             and request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        # Cookies are sent automatically by browsers, so state-changing requests must prove
        # they came from our own JS (cross-site forms cannot set a custom header).
        raise HTTPException(403, "Missing CSRF header")
    claims = decode_token(token, request.app.state.secret) if token else None
    user = db.get(User, claims["uid"]) if claims and "uid" in claims else None
    # Password change (pv) or deactivation invalidates outstanding tokens.
    if user is None or not user.is_active or claims.get("pv") != user.password_hash[-16:]:
        raise HTTPException(401, "Invalid or expired credentials",
                            headers={"WWW-Authenticate": "Bearer"})
    return user


def admin_only(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "District administrator access required")
    return user


def facility_access(facility_id: int, user: User = Depends(current_user),
                    db: Session = Depends(get_db)) -> Facility:
    """Staff may only touch their own facility; admins may touch any."""
    if user.role != "admin" and user.facility_id != facility_id:
        raise HTTPException(403, "You may only access your own facility")
    facility = db.get(Facility, facility_id)
    if facility is None:
        raise HTTPException(404, "Facility not found")
    return facility


def lang_of(request: Request, lang: str | None = Query(None, max_length=20)) -> str:
    return resolve_lang(lang or request.headers.get("Accept-Language"))


def today_of(request: Request) -> date:
    return request.app.state.clock()


def _day(requested: date | None, today: date) -> date:
    day = requested or today
    if day > today:
        raise HTTPException(422, "date cannot be in the future")
    if day < today - timedelta(days=MAX_BACKDATE_DAYS):
        raise HTTPException(422, "date is too far in the past")
    return day


def _upsert(db: Session, model, keys: dict, values: dict) -> None:
    """Insert or update one row; safe against two concurrent first-writers."""
    for attempt in (1, 2):
        row = db.scalar(select(model).filter_by(**keys))
        if row is not None:
            for k, v in values.items():
                setattr(row, k, v)
            return
        try:
            with db.begin_nested():
                db.add(model(**keys, **values))
                db.flush()
            return
        except IntegrityError:
            if attempt == 2:
                raise


# --------------------------------------------------------------------------- routes
router = APIRouter(prefix="/api")


@router.get("/health")
def health(request: Request):
    """Liveness/readiness probe: unauthenticated, reveals nothing beyond up/down."""
    try:
        with request.app.state.session_factory() as db:
            db.execute(text("SELECT 1"))
    except Exception:
        log.exception("health check failed")
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return {"status": "ok"}


@router.post("/auth/login")
def login(body: schemas.LoginIn, request: Request, response: Response,
          db: Session = Depends(get_db)):
    app, ip = request.app, _client_ip(request)
    ukey, ikey = f"u:{body.username.lower()}", f"ip:{ip}"
    if app.state.user_throttle.blocked(ukey) or app.state.ip_throttle.blocked(ikey):
        audit.warning("login throttled user=%s ip=%s", body.username, ip)
        raise HTTPException(429, "Too many failed attempts; try again later")

    user = db.scalar(select(User).where(User.username == body.username))
    ok = verify_password(body.password, user.password_hash if user else _dummy_hash())
    if not (user and ok and user.is_active):
        app.state.user_throttle.record_failure(ukey)
        app.state.ip_throttle.record_failure(ikey)
        audit.warning("login failed user=%s ip=%s", body.username, ip)
        raise HTTPException(401, "Invalid username or password")

    app.state.user_throttle.reset(ukey)
    audit.info("login ok user=%s role=%s ip=%s", user.username, user.role, ip)
    token = create_token({"uid": user.id, "pv": user.password_hash[-16:]},
                         app.state.secret, config.TOKEN_TTL_SECONDS)
    # Browsers authenticate via this HttpOnly cookie (invisible to JS, so XSS can't steal it).
    # The token is also returned for non-browser API clients.
    response.set_cookie(COOKIE_NAME, token, max_age=config.TOKEN_TTL_SECONDS, httponly=True,
                        secure=config.COOKIE_SECURE, samesite="strict", path="/api")
    return {"token": token, "role": user.role, "facility_id": user.facility_id,
            "username": user.username}


@router.post("/auth/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/api")


@router.get("/facilities")
def list_facilities(user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Facility).order_by(Facility.name)
    if user.role != "admin":
        q = q.where(Facility.id == user.facility_id)
    return [{"id": f.id, "name": f.name, "type": f.type, "district": f.district}
            for f in db.scalars(q)]


@router.get("/medicines")
def list_medicines(_: User = Depends(current_user), db: Session = Depends(get_db)):
    return [{"id": m.id, "name": m.name, "unit": m.unit}
            for m in db.scalars(select(Medicine).order_by(Medicine.name))]


# ---- data entry -----------------------------------------------------------------
def _save(db: Session, user: User, facility: Facility, kind: str) -> dict:
    db.commit()
    audit.info("report kind=%s facility=%s user=%s", kind, facility.id, user.username)
    return {"status": "recorded"}


@router.post("/facilities/{facility_id}/stock", status_code=201)
def report_stock(body: schemas.StockIn, facility: Facility = Depends(facility_access),
                 user: User = Depends(current_user), db: Session = Depends(get_db),
                 today: date = Depends(today_of)):
    day = _day(body.day, today)
    if db.get(Medicine, body.medicine_id) is None:
        raise HTTPException(404, "Medicine not found")
    _upsert(db, StockLog,
            {"facility_id": facility.id, "medicine_id": body.medicine_id, "day": day},
            {"closing_qty": body.closing_qty, "consumed": body.consumed})
    return _save(db, user, facility, "stock")


@router.post("/facilities/{facility_id}/footfall", status_code=201)
def report_footfall(body: schemas.FootfallIn, facility: Facility = Depends(facility_access),
                    user: User = Depends(current_user), db: Session = Depends(get_db),
                    today: date = Depends(today_of)):
    _upsert(db, Footfall, {"facility_id": facility.id, "day": _day(body.day, today)},
            {"patients": body.patients})
    return _save(db, user, facility, "footfall")


@router.post("/facilities/{facility_id}/beds", status_code=201)
def report_beds(body: schemas.BedsIn, facility: Facility = Depends(facility_access),
                user: User = Depends(current_user), db: Session = Depends(get_db),
                today: date = Depends(today_of)):
    _upsert(db, BedStatus, {"facility_id": facility.id, "day": _day(body.day, today)},
            {"total": body.total, "occupied": body.occupied})
    return _save(db, user, facility, "beds")


@router.post("/facilities/{facility_id}/attendance", status_code=201)
def report_attendance(body: schemas.AttendanceIn, facility: Facility = Depends(facility_access),
                      user: User = Depends(current_user), db: Session = Depends(get_db),
                      today: date = Depends(today_of)):
    _upsert(db, DoctorAttendance,
            {"facility_id": facility.id, "doctor_name": body.doctor_name,
             "day": _day(body.day, today)},
            {"present": body.present})
    return _save(db, user, facility, "attendance")


@router.post("/facilities/{facility_id}/tests", status_code=201)
def report_test_audit(body: schemas.TestAuditIn, facility: Facility = Depends(facility_access),
                      user: User = Depends(current_user), db: Session = Depends(get_db),
                      today: date = Depends(today_of)):
    _upsert(db, TestAvailability,
            {"facility_id": facility.id, "test_name": body.test_name},
            {"available": body.available, "audited_on": today})
    return _save(db, user, facility, "tests")


# ---- read models ------------------------------------------------------------------
def _warning_rows(state, lang: str) -> list[dict]:
    rows = []
    for fid, mid, a in state.assessments:
        if a.level == "ok":
            continue
        med, fac = state.medicines[mid], state.facilities[fid]
        if a.on_hand == 0:
            msg = t(lang, "stockout_empty", medicine=med.name, facility=fac.name)
        else:
            msg = t(lang, "stockout", medicine=med.name, facility=fac.name,
                    days=a.days_of_cover)
        rows.append({
            "facility_id": fid, "facility": fac.name, "medicine_id": mid, "medicine": med.name,
            "on_hand": a.on_hand, "unit": med.unit, "daily_demand": round(a.daily_demand, 1),
            "days_of_cover": a.days_of_cover, "level": a.level,
            "level_label": t(lang, f"level_{a.level}"), "reorder_qty": a.reorder_qty,
            "message": msg,
        })
    rows.sort(key=lambda r: (r["days_of_cover"] if r["days_of_cover"] is not None else 1e9))
    return rows


def _footfall_series(state, today: date, facility_id: int | None, days: int = 14) -> list[dict]:
    """Daily patient totals for one facility (or the whole scope), oldest first."""
    ids = [facility_id] if facility_id is not None else list(state.facilities)
    out = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        out.append({"day": d.isoformat(),
                    "patients": sum(state.footfall[f].get(d, 0) for f in ids)})
    return out


def _flag_row(state, fid: int, lang: str) -> dict:
    f, flag = state.facilities[fid], state.flags[fid]
    return {
        "facility_id": fid, "facility": f.name, "type": f.type, "score": flag.score,
        "flagged": flag.flagged, "severity": flag.severity,
        "reasons": [{"code": r.code, "points": r.points, "message": t(lang, r.code, **r.params)}
                    for r in flag.reasons],
    }


@router.get("/district/dashboard")
def dashboard(district: str | None = Query(None, max_length=80), _: User = Depends(admin_only),
              db: Session = Depends(get_db), lang: str = Depends(lang_of),
              today: date = Depends(today_of)):
    state = compute_district(db, today, district)
    warnings = _warning_rows(state, lang)
    facilities = []
    for fid, f in state.facilities.items():
        beds, m = state.beds[fid], state.metrics[fid]
        facilities.append({
            "id": fid, "name": f.name, "type": f.type,
            "beds_total": beds[0] if beds else None,
            "beds_occupied": beds[1] if beds else None,
            "attendance_rate": m.attendance_rate, "test_availability": m.test_availability,
            "critical_stock": m.critical_stock,
            "missing_tests": sorted(n for n, ok in state.tests[fid] if not ok),
            "score": state.flags[fid].score,
            "flagged": state.flags[fid].flagged, "severity": state.flags[fid].severity,
        })
    facilities.sort(key=lambda r: -r["score"])
    return {
        "as_of": today.isoformat(),
        "summary": {
            "facilities": len(facilities),
            "flagged": sum(f["flagged"] for f in facilities),
            "critical_stockouts": sum(w["level"] == "critical" for w in warnings),
            "beds_total": sum(f["beds_total"] or 0 for f in facilities),
            "beds_occupied": sum(f["beds_occupied"] or 0 for f in facilities),
        },
        "footfall_trend": _footfall_series(state, today, None),
        "facilities": facilities,
    }


@router.get("/district/stockout-warnings")
def stockout_warnings(district: str | None = Query(None, max_length=80),
                      _: User = Depends(admin_only), db: Session = Depends(get_db),
                      lang: str = Depends(lang_of), today: date = Depends(today_of)):
    return _warning_rows(compute_district(db, today, district), lang)


@router.get("/district/redistribution")
def redistribution(district: str | None = Query(None, max_length=80),
                   _: User = Depends(admin_only), db: Session = Depends(get_db),
                   lang: str = Depends(lang_of), today: date = Depends(today_of)):
    state = compute_district(db, today, district)
    out = []
    for tr in analytics.plan_transfers(state.positions):
        med = state.medicines[tr.medicine_id]
        src, dst = state.facilities[tr.source_id], state.facilities[tr.target_id]
        out.append({
            "medicine": med.name, "unit": med.unit, "quantity": tr.quantity,
            "source": src.name, "source_id": src.id, "target": dst.name, "target_id": dst.id,
            "distance_km": tr.distance_km,
            "message": t(lang, "transfer", qty=tr.quantity, unit=med.unit, medicine=med.name,
                         source=src.name, target=dst.name, km=tr.distance_km),
        })
    return out


@router.get("/district/flags")
def flags(district: str | None = Query(None, max_length=80), all: bool = False,
          _: User = Depends(admin_only), db: Session = Depends(get_db),
          lang: str = Depends(lang_of), today: date = Depends(today_of)):
    state = compute_district(db, today, district)
    rows = [_flag_row(state, fid, lang) for fid in state.facilities
            if all or state.flags[fid].flagged]
    return sorted(rows, key=lambda r: -r["score"])


@router.get("/facilities/{facility_id}/overview")
def facility_overview(facility: Facility = Depends(facility_access), db: Session = Depends(get_db),
                      lang: str = Depends(lang_of), today: date = Depends(today_of)):
    state = compute_district(db, today, facility_id=facility.id)
    beds = state.beds[facility.id]
    return {
        "facility": {"id": facility.id, "name": facility.name, "type": facility.type},
        "beds": {"total": beds[0], "occupied": beds[1]} if beds else None,
        "stock": _warning_rows(state, lang),
        "tests": [{"name": n, "available": ok} for n, ok in sorted(state.tests[facility.id])],
        "footfall": _footfall_series(state, today, facility.id),
        "flag": _flag_row(state, facility.id, lang),
    }


@router.get("/facilities/{facility_id}/forecast")
def forecast(medicine_id: int = Query(gt=0), days: int = Query(config.FORECAST_HORIZON, ge=1, le=60),
             facility: Facility = Depends(facility_access), db: Session = Depends(get_db),
             today: date = Depends(today_of)):
    med = db.get(Medicine, medicine_id)
    if med is None:
        raise HTTPException(404, "Medicine not found")
    logs = list(db.scalars(
        select(StockLog)
        .where(StockLog.facility_id == facility.id, StockLog.medicine_id == medicine_id,
               StockLog.day >= today - timedelta(days=config.HISTORY_DAYS), StockLog.day <= today)
        .order_by(StockLog.day)))
    if not logs:
        raise HTTPException(404, "No stock history for this medicine at this facility")
    a = analytics.assess_stock(logs[-1].closing_qty, [float(x.consumed) for x in logs], horizon=days)
    return {
        "medicine": med.name, "unit": med.unit, "on_hand": a.on_hand, "level": a.level,
        "days_of_cover": a.days_of_cover, "daily_demand": round(a.daily_demand, 2),
        "reorder_qty": a.reorder_qty,
        "history": [{"day": x.day.isoformat(), "consumed": x.consumed} for x in logs],
        "forecast": [{"day": (today + timedelta(days=i + 1)).isoformat(), "demand": round(v, 2)}
                     for i, v in enumerate(a.forecast)],
    }


# --------------------------------------------------------------------------- factory
def create_app(database_url: str | None = None, secret: str | None = None,
               clock: Callable[[], date] = config.local_today) -> FastAPI:
    if not logging.getLogger().handlers:
        logging.basicConfig(level=config.LOG_LEVEL,
                            format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if config.IS_PROD:
        problems = config.production_problems(secret or config.SECRET_KEY,
                                              bool(secret) or config.SECRET_FROM_ENV,
                                              config.COOKIE_SECURE)
        if problems:
            raise RuntimeError("Unsafe production configuration:\n - " + "\n - ".join(problems))
        if not config.ALLOWED_HOSTS:
            log.warning("SMARTHEALTH_ALLOWED_HOSTS is not set; Host header is not validated")

    engine = make_engine(database_url)
    if not config.IS_PROD:  # production schemas are managed by `alembic upgrade head`
        Base.metadata.create_all(engine)

    app = FastAPI(title="Smart Health", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.secret = secret or config.SECRET_KEY
    app.state.clock = clock
    app.state.user_throttle = LoginThrottle(max_failures=5, window=300)
    app.state.ip_throttle = LoginThrottle(max_failures=30, window=300)

    if config.ALLOWED_HOSTS:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=config.ALLOWED_HOSTS)

    @app.middleware("http")
    async def guards_and_headers(request: Request, call_next):
        try:
            too_big = int(request.headers.get("content-length", "0")) > config.MAX_BODY_BYTES
        except ValueError:
            too_big = True
        if too_big:
            return JSONResponse({"detail": "Request body too large"}, status_code=413)
        response = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        if config.COOKIE_SECURE:
            response.headers.setdefault("Strict-Transport-Security",
                                        "max-age=31536000; includeSubDomains")
        # API responses hold private data; static assets just need revalidation.
        response.headers.setdefault(
            "Cache-Control", "no-store" if request.url.path.startswith("/api") else "no-cache")
        return response

    app.include_router(router)
    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app
