"""Data entry: centre staff (or admins) report stock, footfall, beds, attendance and test audits."""
from __future__ import annotations

import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import schemas
from ..deps import current_user, facility_access, get_db, today_of
from ..models import (
    BedStatus,
    DoctorAttendance,
    Facility,
    Footfall,
    Medicine,
    StockLog,
    TestAvailability,
    User,
)

router = APIRouter(prefix="/facilities/{facility_id}")
audit = logging.getLogger("smarthealth.audit")
MAX_BACKDATE_DAYS = 400


def resolve_day(requested: date | None, today: date) -> date:
    """Default to today; reject future dates and implausibly old backfills."""
    day = requested or today
    if day > today:
        raise HTTPException(422, "date cannot be in the future")
    if day < today - timedelta(days=MAX_BACKDATE_DAYS):
        raise HTTPException(422, "date is too far in the past")
    return day


def upsert(db: Session, model, keys: dict, values: dict) -> None:
    """Insert or update one row; safe against two concurrent first-writers."""
    for attempt in (1, 2):
        row = db.scalar(select(model).filter_by(**keys))
        if row is not None:
            for field, value in values.items():
                setattr(row, field, value)
            return
        try:
            with db.begin_nested():
                db.add(model(**keys, **values))
                db.flush()
            return
        except IntegrityError:
            if attempt == 2:
                raise


def _record(db: Session, user: User, facility: Facility, kind: str, model, keys: dict, values: dict) -> dict:
    """Upsert one report, commit, and write the audit trail."""
    upsert(db, model, {"facility_id": facility.id, **keys}, values)
    db.commit()
    audit.info("report kind=%s facility=%s user=%s", kind, facility.id, user.username)
    return {"status": "recorded"}


@router.post("/stock", status_code=201)
def report_stock(body: schemas.StockIn, facility: Facility = Depends(facility_access),
                 user: User = Depends(current_user), db: Session = Depends(get_db),
                 today: date = Depends(today_of)):
    day = resolve_day(body.day, today)
    if db.get(Medicine, body.medicine_id) is None:
        raise HTTPException(404, "Medicine not found")
    return _record(db, user, facility, "stock", StockLog,
                   {"medicine_id": body.medicine_id, "day": day},
                   {"closing_qty": body.closing_qty, "consumed": body.consumed})


@router.post("/footfall", status_code=201)
def report_footfall(body: schemas.FootfallIn, facility: Facility = Depends(facility_access),
                    user: User = Depends(current_user), db: Session = Depends(get_db),
                    today: date = Depends(today_of)):
    return _record(db, user, facility, "footfall", Footfall,
                   {"day": resolve_day(body.day, today)}, {"patients": body.patients})


@router.post("/beds", status_code=201)
def report_beds(body: schemas.BedsIn, facility: Facility = Depends(facility_access),
                user: User = Depends(current_user), db: Session = Depends(get_db),
                today: date = Depends(today_of)):
    return _record(db, user, facility, "beds", BedStatus,
                   {"day": resolve_day(body.day, today)},
                   {"total": body.total, "occupied": body.occupied})


@router.post("/attendance", status_code=201)
def report_attendance(body: schemas.AttendanceIn, facility: Facility = Depends(facility_access),
                      user: User = Depends(current_user), db: Session = Depends(get_db),
                      today: date = Depends(today_of)):
    return _record(db, user, facility, "attendance", DoctorAttendance,
                   {"doctor_name": body.doctor_name, "day": resolve_day(body.day, today)},
                   {"present": body.present})


@router.post("/tests", status_code=201)
def report_test_audit(body: schemas.TestAuditIn, facility: Facility = Depends(facility_access),
                      user: User = Depends(current_user), db: Session = Depends(get_db),
                      today: date = Depends(today_of)):
    return _record(db, user, facility, "tests", TestAvailability,
                   {"test_name": body.test_name},
                   {"available": body.available, "audited_on": today})
