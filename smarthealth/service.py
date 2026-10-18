"""Loads data in a handful of bulk queries and feeds it to the pure analytics layer."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import analytics, config
from .models import (
    BedStatus, DoctorAttendance, Facility, Footfall, Medicine, StockLog, TestAvailability,
)


@dataclass
class DistrictState:
    facilities: dict[int, Facility]
    medicines: dict[int, Medicine]
    assessments: list[tuple[int, int, analytics.StockAssessment]] = field(default_factory=list)
    positions: list[analytics.StockPosition] = field(default_factory=list)
    beds: dict[int, tuple[int, int] | None] = field(default_factory=dict)
    metrics: dict[int, analytics.FacilityMetrics] = field(default_factory=dict)
    flags: dict[int, analytics.FlagResult] = field(default_factory=dict)
    footfall: dict[int, dict[date, int]] = field(default_factory=dict)  # last 17 days
    tests: dict[int, list[tuple[str, bool]]] = field(default_factory=dict)


def compute_district(
    db: Session, today: date, district: str | None = None, facility_id: int | None = None
) -> DistrictState:
    """Compute stock assessments, redistribution inputs and risk flags for a scope.

    `facility_id` narrows the scope to one centre; otherwise the whole district (or all).
    """
    q = select(Facility)
    if facility_id is not None:
        q = q.where(Facility.id == facility_id)
    elif district:
        q = q.where(Facility.district == district)
    facilities = {f.id: f for f in db.scalars(q)}
    medicines = {m.id: m for m in db.scalars(select(Medicine))}
    state = DistrictState(facilities, medicines)
    if not facilities:
        return state
    ids = list(facilities)

    # ---- stock -------------------------------------------------------------
    history: dict[tuple[int, int], list[StockLog]] = defaultdict(list)
    since = today - timedelta(days=config.HISTORY_DAYS)
    for log in db.scalars(
        select(StockLog)
        .where(StockLog.facility_id.in_(ids), StockLog.day >= since, StockLog.day <= today)
        .order_by(StockLog.day)
    ):
        history[(log.facility_id, log.medicine_id)].append(log)

    critical: dict[int, int] = defaultdict(int)
    warning: dict[int, int] = defaultdict(int)
    for (fid, mid), logs in history.items():
        a = analytics.assess_stock(logs[-1].closing_qty, [float(x.consumed) for x in logs])
        state.assessments.append((fid, mid, a))
        f = facilities[fid]
        state.positions.append(
            analytics.StockPosition(fid, mid, a.on_hand, a.daily_demand, f.lat, f.lon)
        )
        if a.level == "critical":
            critical[fid] += 1
        elif a.level == "warning":
            warning[fid] += 1

    last_report: dict[int, date] = {}
    for (fid, _), logs in history.items():
        last_report[fid] = max(last_report.get(fid, logs[-1].day), logs[-1].day)

    # ---- footfall ----------------------------------------------------------
    state.footfall = {fid: {} for fid in ids}
    state.tests = {fid: [] for fid in ids}
    recent: dict[int, list[int]] = defaultdict(list)
    prior: dict[int, list[int]] = defaultdict(list)
    for r in db.scalars(
        select(Footfall).where(
            Footfall.facility_id.in_(ids),
            Footfall.day >= today - timedelta(days=16), Footfall.day <= today,
        )
    ):
        state.footfall[r.facility_id][r.day] = r.patients
        (recent if r.day >= today - timedelta(days=2) else prior)[r.facility_id].append(r.patients)
        last_report[r.facility_id] = max(last_report.get(r.facility_id, r.day), r.day)

    # ---- beds (latest within a week) ----------------------------------------
    latest_bed: dict[int, BedStatus] = {}
    for r in db.scalars(
        select(BedStatus)
        .where(BedStatus.facility_id.in_(ids), BedStatus.day >= today - timedelta(days=7),
               BedStatus.day <= today)
        .order_by(BedStatus.day)
    ):
        latest_bed[r.facility_id] = r
        last_report[r.facility_id] = max(last_report.get(r.facility_id, r.day), r.day)

    # ---- attendance (7 days) -------------------------------------------------
    present: dict[int, int] = defaultdict(int)
    rostered: dict[int, int] = defaultdict(int)
    for r in db.scalars(
        select(DoctorAttendance).where(
            DoctorAttendance.facility_id.in_(ids),
            DoctorAttendance.day >= today - timedelta(days=6), DoctorAttendance.day <= today,
        )
    ):
        rostered[r.facility_id] += 1
        present[r.facility_id] += int(r.present)
        last_report[r.facility_id] = max(last_report.get(r.facility_id, r.day), r.day)

    # ---- diagnostic tests ----------------------------------------------------
    tests_ok: dict[int, int] = defaultdict(int)
    tests_all: dict[int, int] = defaultdict(int)
    for r in db.scalars(select(TestAvailability).where(TestAvailability.facility_id.in_(ids))):
        state.tests[r.facility_id].append((r.test_name, r.available))
        tests_all[r.facility_id] += 1
        tests_ok[r.facility_id] += int(r.available)

    # ---- per-facility metrics and flags -------------------------------------------
    for fid in ids:
        bed = latest_bed.get(fid)
        state.beds[fid] = (bed.total, bed.occupied) if bed else None
        base = sum(prior[fid]) / len(prior[fid]) if len(prior[fid]) >= 3 else None
        ratio = (
            (sum(recent[fid]) / len(recent[fid])) / base
            if recent[fid] and base else None
        )
        last = last_report.get(fid)
        m = analytics.FacilityMetrics(
            critical_stock=critical[fid],
            warning_stock=warning[fid],
            bed_occupancy=(bed.occupied / bed.total) if bed and bed.total else None,
            attendance_rate=(present[fid] / rostered[fid]) if rostered[fid] else None,
            test_availability=(tests_ok[fid] / tests_all[fid]) if tests_all[fid] else None,
            footfall_ratio=ratio,
            days_since_report=(today - last).days if last else config.HISTORY_DAYS,
        )
        state.metrics[fid] = m
        state.flags[fid] = analytics.score_facility(m)
    return state
