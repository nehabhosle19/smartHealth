"""Loads data in a handful of bulk queries and feeds it to the pure analytics layer."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import analytics, config
from .models import (
    BedStatus,
    DoctorAttendance,
    Facility,
    Footfall,
    Medicine,
    StockLog,
    TestAvailability,
)

FOOTFALL_WINDOW_DAYS = 17      # 3 recent days + 14 baseline days
FOOTFALL_RECENT_DAYS = 3
FOOTFALL_MIN_BASELINE_POINTS = 3
BED_LOOKBACK_DAYS = 7
ATTENDANCE_WINDOW_DAYS = 7


@dataclass
class DistrictState:
    facilities: dict[int, Facility]
    medicines: dict[int, Medicine]
    assessments: list[tuple[int, int, analytics.StockAssessment]] = field(default_factory=list)
    positions: list[analytics.StockPosition] = field(default_factory=list)
    beds: dict[int, tuple[int, int] | None] = field(default_factory=dict)
    metrics: dict[int, analytics.FacilityMetrics] = field(default_factory=dict)
    flags: dict[int, analytics.FlagResult] = field(default_factory=dict)
    footfall: dict[int, dict[date, int]] = field(default_factory=dict)
    tests: dict[int, list[tuple[str, bool]]] = field(default_factory=dict)


@dataclass
class _Signals:
    """Raw per-facility inputs gathered from the database before scoring."""

    critical: dict[int, int] = field(default_factory=lambda: defaultdict(int))
    warning: dict[int, int] = field(default_factory=lambda: defaultdict(int))
    last_report: dict[int, date] = field(default_factory=dict)
    recent_footfall: dict[int, list[int]] = field(default_factory=lambda: defaultdict(list))
    baseline_footfall: dict[int, list[int]] = field(default_factory=lambda: defaultdict(list))
    present: dict[int, int] = field(default_factory=lambda: defaultdict(int))
    rostered: dict[int, int] = field(default_factory=lambda: defaultdict(int))
    tests_ok: dict[int, int] = field(default_factory=lambda: defaultdict(int))
    tests_all: dict[int, int] = field(default_factory=lambda: defaultdict(int))

    def seen(self, facility_id: int, day: date) -> None:
        if day > self.last_report.get(facility_id, date.min):
            self.last_report[facility_id] = day


def _in_scope(district: str | None, facility_id: int | None):
    query = select(Facility)
    if facility_id is not None:
        return query.where(Facility.id == facility_id)
    if district:
        return query.where(Facility.district == district)
    return query


def _load_stock(db: Session, state: DistrictState, signals: _Signals, ids: list[int], today: date) -> None:
    history: dict[tuple[int, int], list[StockLog]] = defaultdict(list)
    since = today - timedelta(days=config.HISTORY_DAYS)
    rows = db.scalars(
        select(StockLog)
        .where(StockLog.facility_id.in_(ids), StockLog.day >= since, StockLog.day <= today)
        .order_by(StockLog.day)
    )
    for log in rows:
        history[(log.facility_id, log.medicine_id)].append(log)

    for (facility_id, medicine_id), logs in history.items():
        assessment = analytics.assess_stock(logs[-1].closing_qty, [float(x.consumed) for x in logs])
        facility = state.facilities[facility_id]
        state.assessments.append((facility_id, medicine_id, assessment))
        state.positions.append(analytics.StockPosition(
            facility_id, medicine_id, assessment.on_hand, assessment.daily_demand, facility.lat, facility.lon))
        if assessment.level == "critical":
            signals.critical[facility_id] += 1
        elif assessment.level == "warning":
            signals.warning[facility_id] += 1
        signals.seen(facility_id, logs[-1].day)


def _load_footfall(db: Session, state: DistrictState, signals: _Signals, ids: list[int], today: date) -> None:
    recent_from = today - timedelta(days=FOOTFALL_RECENT_DAYS - 1)
    rows = db.scalars(select(Footfall).where(
        Footfall.facility_id.in_(ids),
        Footfall.day >= today - timedelta(days=FOOTFALL_WINDOW_DAYS - 1), Footfall.day <= today))
    for row in rows:
        state.footfall[row.facility_id][row.day] = row.patients
        bucket = signals.recent_footfall if row.day >= recent_from else signals.baseline_footfall
        bucket[row.facility_id].append(row.patients)
        signals.seen(row.facility_id, row.day)


def _load_beds(db: Session, state: DistrictState, signals: _Signals, ids: list[int], today: date) -> None:
    latest: dict[int, BedStatus] = {}
    rows = db.scalars(
        select(BedStatus)
        .where(BedStatus.facility_id.in_(ids), BedStatus.day >= today - timedelta(days=BED_LOOKBACK_DAYS),
               BedStatus.day <= today)
        .order_by(BedStatus.day)
    )
    for row in rows:
        latest[row.facility_id] = row
        signals.seen(row.facility_id, row.day)
    for facility_id in ids:
        bed = latest.get(facility_id)
        state.beds[facility_id] = (bed.total, bed.occupied) if bed else None


def _load_attendance(db: Session, signals: _Signals, ids: list[int], today: date) -> None:
    rows = db.scalars(select(DoctorAttendance).where(
        DoctorAttendance.facility_id.in_(ids),
        DoctorAttendance.day >= today - timedelta(days=ATTENDANCE_WINDOW_DAYS - 1),
        DoctorAttendance.day <= today))
    for row in rows:
        signals.rostered[row.facility_id] += 1
        signals.present[row.facility_id] += int(row.present)
        signals.seen(row.facility_id, row.day)


def _load_tests(db: Session, state: DistrictState, signals: _Signals, ids: list[int]) -> None:
    for row in db.scalars(select(TestAvailability).where(TestAvailability.facility_id.in_(ids))):
        state.tests[row.facility_id].append((row.test_name, row.available))
        signals.tests_all[row.facility_id] += 1
        signals.tests_ok[row.facility_id] += int(row.available)


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _footfall_ratio(signals: _Signals, facility_id: int) -> float | None:
    """Mean of the last few days relative to the preceding baseline (None if too little data)."""
    recent, baseline = signals.recent_footfall[facility_id], signals.baseline_footfall[facility_id]
    if not recent or len(baseline) < FOOTFALL_MIN_BASELINE_POINTS:
        return None
    baseline_mean = sum(baseline) / len(baseline)
    return (sum(recent) / len(recent)) / baseline_mean if baseline_mean else None


def _metrics_for(state: DistrictState, signals: _Signals, facility_id: int, today: date) -> analytics.FacilityMetrics:
    beds = state.beds[facility_id]
    last = signals.last_report.get(facility_id)
    return analytics.FacilityMetrics(
        critical_stock=signals.critical[facility_id],
        warning_stock=signals.warning[facility_id],
        bed_occupancy=_ratio(beds[1], beds[0]) if beds else None,
        attendance_rate=_ratio(signals.present[facility_id], signals.rostered[facility_id]),
        test_availability=_ratio(signals.tests_ok[facility_id], signals.tests_all[facility_id]),
        footfall_ratio=_footfall_ratio(signals, facility_id),
        days_since_report=(today - last).days if last else config.HISTORY_DAYS,
    )


def compute_district(
    db: Session, today: date, district: str | None = None, facility_id: int | None = None
) -> DistrictState:
    """Compute stock assessments, redistribution inputs and risk flags for a scope.

    `facility_id` narrows the scope to one centre; otherwise the whole district (or all).
    """
    facilities = {f.id: f for f in db.scalars(_in_scope(district, facility_id))}
    state = DistrictState(facilities, {m.id: m for m in db.scalars(select(Medicine))})
    if not facilities:
        return state

    ids = list(facilities)
    state.footfall = {fid: {} for fid in ids}
    state.tests = {fid: [] for fid in ids}
    signals = _Signals()
    _load_stock(db, state, signals, ids, today)
    _load_footfall(db, state, signals, ids, today)
    _load_beds(db, state, signals, ids, today)
    _load_attendance(db, signals, ids, today)
    _load_tests(db, state, signals, ids)

    for fid in ids:
        state.metrics[fid] = _metrics_for(state, signals, fid, today)
        state.flags[fid] = analytics.score_facility(state.metrics[fid])
    return state
