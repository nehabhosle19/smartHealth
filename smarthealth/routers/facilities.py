"""Facility lookups, per-facility overview and demand forecast."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import analytics, config, presenters
from ..deps import current_user, facility_access, get_db, lang_of, today_of
from ..models import Facility, Medicine, StockLog, User
from ..service import compute_district

router = APIRouter()


@router.get("/facilities")
def list_facilities(user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = select(Facility).order_by(Facility.name)
    if user.role != "admin":
        query = query.where(Facility.id == user.facility_id)
    return [{"id": f.id, "name": f.name, "type": f.type, "district": f.district}
            for f in db.scalars(query)]


@router.get("/medicines")
def list_medicines(_: User = Depends(current_user), db: Session = Depends(get_db)):
    return [{"id": m.id, "name": m.name, "unit": m.unit}
            for m in db.scalars(select(Medicine).order_by(Medicine.name))]


@router.get("/facilities/{facility_id}/overview")
def facility_overview(facility: Facility = Depends(facility_access), db: Session = Depends(get_db),
                      lang: str = Depends(lang_of), today: date = Depends(today_of)):
    state = compute_district(db, today, facility_id=facility.id)
    return presenters.facility_overview(state, today, facility.id, lang)


@router.get("/facilities/{facility_id}/forecast")
def forecast(medicine_id: int = Query(gt=0),
             days: int = Query(config.FORECAST_HORIZON, ge=1, le=60),
             facility: Facility = Depends(facility_access), db: Session = Depends(get_db),
             today: date = Depends(today_of)):
    medicine = db.get(Medicine, medicine_id)
    if medicine is None:
        raise HTTPException(404, "Medicine not found")
    logs = list(db.scalars(
        select(StockLog)
        .where(StockLog.facility_id == facility.id, StockLog.medicine_id == medicine_id,
               StockLog.day >= today - timedelta(days=config.HISTORY_DAYS), StockLog.day <= today)
        .order_by(StockLog.day)))
    if not logs:
        raise HTTPException(404, "No stock history for this medicine at this facility")
    assessment = analytics.assess_stock(logs[-1].closing_qty, [float(x.consumed) for x in logs], horizon=days)
    return presenters.forecast_payload(medicine, logs, assessment, today)
