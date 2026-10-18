"""District-wide views for administrators."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import presenters
from ..deps import admin_only, get_db, lang_of, today_of
from ..service import compute_district

router = APIRouter(prefix="/district", dependencies=[Depends(admin_only)])

DistrictFilter = Query(None, max_length=80, description="Restrict to one district")


@router.get("/dashboard")
def dashboard(district: str | None = DistrictFilter, db: Session = Depends(get_db),
              lang: str = Depends(lang_of), today: date = Depends(today_of)):
    return presenters.dashboard(compute_district(db, today, district), today, lang)


@router.get("/stockout-warnings")
def stockout_warnings(district: str | None = DistrictFilter, db: Session = Depends(get_db),
                      lang: str = Depends(lang_of), today: date = Depends(today_of)):
    return presenters.warning_rows(compute_district(db, today, district), lang)


@router.get("/redistribution")
def redistribution(district: str | None = DistrictFilter, db: Session = Depends(get_db),
                   lang: str = Depends(lang_of), today: date = Depends(today_of)):
    return presenters.transfer_rows(compute_district(db, today, district), lang)


@router.get("/flags")
def flags(district: str | None = DistrictFilter,
          include_all: bool = Query(False, alias="all", description="Include unflagged centres too"),
          db: Session = Depends(get_db), lang: str = Depends(lang_of), today: date = Depends(today_of)):
    state = compute_district(db, today, district)
    rows = [presenters.flag_row(state, fid, lang) for fid in state.facilities
            if include_all or state.flags[fid].flagged]
    return sorted(rows, key=lambda row: -row["score"])
