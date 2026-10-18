"""Turns computed district state into translated JSON-ready dictionaries.

Kept separate from the routers so the HTTP layer stays thin and these builders can be tested
or reused without a request.
"""
from __future__ import annotations

from datetime import date, timedelta

from . import analytics
from .i18n import t
from .service import DistrictState

FOOTFALL_TREND_DAYS = 14
NO_COVER_SORT_KEY = 1e9  # medicines without measurable demand sort last


def warning_rows(state: DistrictState, lang: str) -> list[dict]:
    """Stock-out warnings (critical/warning only), most urgent first."""
    rows = []
    for facility_id, medicine_id, a in state.assessments:
        if a.level == "ok":
            continue
        med, fac = state.medicines[medicine_id], state.facilities[facility_id]
        if a.on_hand == 0:
            message = t(lang, "stockout_empty", medicine=med.name, facility=fac.name)
        else:
            message = t(lang, "stockout", medicine=med.name, facility=fac.name, days=a.days_of_cover)
        rows.append({
            "facility_id": facility_id, "facility": fac.name,
            "medicine_id": medicine_id, "medicine": med.name, "unit": med.unit,
            "on_hand": a.on_hand, "daily_demand": round(a.daily_demand, 1),
            "days_of_cover": a.days_of_cover, "reorder_qty": a.reorder_qty,
            "level": a.level, "level_label": t(lang, f"level_{a.level}"), "message": message,
        })
    rows.sort(key=lambda r: NO_COVER_SORT_KEY if r["days_of_cover"] is None else r["days_of_cover"])
    return rows


def footfall_series(
    state: DistrictState, today: date, facility_id: int | None = None, days: int = FOOTFALL_TREND_DAYS
) -> list[dict]:
    """Daily patient totals for one facility (or the whole scope), oldest first."""
    ids = [facility_id] if facility_id is not None else list(state.facilities)
    series = []
    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        series.append({"day": day.isoformat(),
                       "patients": sum(state.footfall[fid].get(day, 0) for fid in ids)})
    return series


def flag_row(state: DistrictState, facility_id: int, lang: str) -> dict:
    facility, flag = state.facilities[facility_id], state.flags[facility_id]
    return {
        "facility_id": facility_id, "facility": facility.name, "type": facility.type,
        "score": flag.score, "flagged": flag.flagged, "severity": flag.severity,
        "reasons": [{"code": r.code, "points": r.points, "message": t(lang, r.code, **r.params)}
                    for r in flag.reasons],
    }


def _facility_summary(state: DistrictState, facility_id: int) -> dict:
    facility, metrics, flag = state.facilities[facility_id], state.metrics[facility_id], state.flags[facility_id]
    beds = state.beds[facility_id]
    return {
        "id": facility_id, "name": facility.name, "type": facility.type,
        "beds_total": beds[0] if beds else None, "beds_occupied": beds[1] if beds else None,
        "attendance_rate": metrics.attendance_rate, "test_availability": metrics.test_availability,
        "critical_stock": metrics.critical_stock,
        "missing_tests": sorted(name for name, ok in state.tests[facility_id] if not ok),
        "score": flag.score, "flagged": flag.flagged, "severity": flag.severity,
    }


def dashboard(state: DistrictState, today: date, lang: str) -> dict:
    warnings = warning_rows(state, lang)
    facilities = sorted((_facility_summary(state, fid) for fid in state.facilities),
                        key=lambda f: -f["score"])
    return {
        "as_of": today.isoformat(),
        "summary": {
            "facilities": len(facilities),
            "flagged": sum(f["flagged"] for f in facilities),
            "critical_stockouts": sum(w["level"] == "critical" for w in warnings),
            "beds_total": sum(f["beds_total"] or 0 for f in facilities),
            "beds_occupied": sum(f["beds_occupied"] or 0 for f in facilities),
        },
        "footfall_trend": footfall_series(state, today),
        "facilities": facilities,
    }


def facility_overview(state: DistrictState, today: date, facility_id: int, lang: str) -> dict:
    facility, beds = state.facilities[facility_id], state.beds[facility_id]
    return {
        "facility": {"id": facility.id, "name": facility.name, "type": facility.type},
        "beds": {"total": beds[0], "occupied": beds[1]} if beds else None,
        "stock": warning_rows(state, lang),
        "tests": [{"name": name, "available": ok} for name, ok in sorted(state.tests[facility_id])],
        "footfall": footfall_series(state, today, facility_id),
        "flag": flag_row(state, facility_id, lang),
    }


def transfer_rows(state: DistrictState, lang: str) -> list[dict]:
    rows = []
    for transfer in analytics.plan_transfers(state.positions):
        med = state.medicines[transfer.medicine_id]
        source, target = state.facilities[transfer.source_id], state.facilities[transfer.target_id]
        rows.append({
            "medicine": med.name, "unit": med.unit, "quantity": transfer.quantity,
            "source": source.name, "source_id": source.id,
            "target": target.name, "target_id": target.id,
            "distance_km": transfer.distance_km,
            "message": t(lang, "transfer", qty=transfer.quantity, unit=med.unit, medicine=med.name,
                         source=source.name, target=target.name, km=transfer.distance_km),
        })
    return rows


def forecast_payload(medicine, logs: list, assessment: analytics.StockAssessment, today: date) -> dict:
    return {
        "medicine": medicine.name, "unit": medicine.unit, "on_hand": assessment.on_hand,
        "level": assessment.level, "days_of_cover": assessment.days_of_cover,
        "daily_demand": round(assessment.daily_demand, 2), "reorder_qty": assessment.reorder_qty,
        "history": [{"day": log.day.isoformat(), "consumed": log.consumed} for log in logs],
        "forecast": [{"day": (today + timedelta(days=i + 1)).isoformat(), "demand": round(v, 2)}
                     for i, v in enumerate(assessment.forecast)],
    }
