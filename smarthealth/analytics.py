"""Pure analytics: demand forecasting, stock-out risk, redistribution, facility scoring.

Nothing here touches the database, so every function is deterministic and unit-testable.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import config


# --------------------------------------------------------------------------- forecasting
def holt_forecast(
    series: list[float], horizon: int, alpha: float = 0.4, beta: float = 0.15, phi: float = 0.9
) -> list[float]:
    """Holt's damped-trend exponential smoothing; forecasts are clamped at zero.

    Damping keeps long-horizon forecasts from extrapolating a short-term trend wildly.
    """
    if horizon <= 0:
        return []
    if not series:
        return [0.0] * horizon
    if len(series) < 3:
        mean = sum(series) / len(series)
        return [max(0.0, mean)] * horizon

    level, trend = series[0], series[1] - series[0]
    for y in series[1:]:
        prev_level = level
        level = alpha * y + (1 - alpha) * (prev_level + phi * trend)
        trend = beta * (level - prev_level) + (1 - beta) * phi * trend

    out, damp = [], 0.0
    for h in range(1, horizon + 1):
        damp += phi**h
        out.append(max(0.0, level + damp * trend))
    return out


@dataclass(frozen=True)
class StockAssessment:
    on_hand: int
    daily_demand: float
    days_of_cover: float | None  # None -> no measurable demand
    level: str  # critical | warning | ok
    forecast: list[float] = field(default_factory=list)
    reorder_qty: int = 0


def assess_stock(
    on_hand: int,
    consumption: list[float],
    horizon: int = config.FORECAST_HORIZON,
    lead_time: int = config.LEAD_TIME_DAYS,
) -> StockAssessment:
    forecast = holt_forecast(consumption, horizon)
    daily = sum(forecast) / horizon if horizon else 0.0
    if daily <= 1e-9:
        return StockAssessment(on_hand, 0.0, None, "ok", forecast, 0)

    cover = on_hand / daily
    if cover < config.CRITICAL_COVER_DAYS:
        level = "critical"
    elif cover < lead_time:
        level = "warning"
    else:
        level = "ok"
    reorder = max(0, math.ceil(daily * config.TARGET_COVER_DAYS - on_hand))
    return StockAssessment(on_hand, daily, round(cover, 1), level, forecast, reorder)


# --------------------------------------------------------------------------- redistribution
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dlmb = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


@dataclass(frozen=True)
class StockPosition:
    facility_id: int
    medicine_id: int
    on_hand: int
    daily_demand: float
    lat: float
    lon: float


@dataclass(frozen=True)
class Transfer:
    medicine_id: int
    source_id: int
    target_id: int
    quantity: int
    distance_km: float


def plan_transfers(positions: list[StockPosition]) -> list[Transfer]:
    """Greedy redistribution: most urgent deficits first, nearest eligible donors first.

    A facility is a *deficit* if its cover is below the replenishment lead time, and a
    *donor* only if its cover exceeds DONOR_MIN_COVER_DAYS; donors never drop below
    DONOR_RESERVE_DAYS of cover (or 20% of stock when demand is unmeasurable).
    """
    by_med: dict[int, list[StockPosition]] = {}
    for p in positions:
        by_med.setdefault(p.medicine_id, []).append(p)

    transfers: list[Transfer] = []
    for med_id, group in by_med.items():
        surplus: dict[int, int] = {}
        for p in group:
            if p.daily_demand > 1e-9 and p.on_hand / p.daily_demand <= config.DONOR_MIN_COVER_DAYS:
                continue
            reserve = max(p.daily_demand * config.DONOR_RESERVE_DAYS, 0.2 * p.on_hand)
            spare = math.floor(p.on_hand - reserve)
            if spare > 0:
                surplus[p.facility_id] = spare

        deficits = [
            p for p in group
            if p.daily_demand > 1e-9 and p.on_hand / p.daily_demand < config.LEAD_TIME_DAYS
        ]
        deficits.sort(key=lambda p: p.on_hand / p.daily_demand)
        donors = {p.facility_id: p for p in group if p.facility_id in surplus}

        for need_pos in deficits:
            need = math.ceil(need_pos.daily_demand * config.TARGET_COVER_DAYS - need_pos.on_hand)
            ranked = sorted(
                donors.values(),
                key=lambda d: haversine_km(d.lat, d.lon, need_pos.lat, need_pos.lon),
            )
            for donor in ranked:
                if need <= 0:
                    break
                give = min(need, surplus.get(donor.facility_id, 0))
                if give <= 0:
                    continue
                surplus[donor.facility_id] -= give
                need -= give
                transfers.append(
                    Transfer(
                        med_id, donor.facility_id, need_pos.facility_id, give,
                        round(haversine_km(donor.lat, donor.lon, need_pos.lat, need_pos.lon), 1),
                    )
                )
    return transfers


# --------------------------------------------------------------------------- facility scoring
@dataclass(frozen=True)
class FacilityMetrics:
    critical_stock: int = 0
    warning_stock: int = 0
    bed_occupancy: float | None = None      # 0..1
    attendance_rate: float | None = None    # 0..1 over the last 7 days
    test_availability: float | None = None  # 0..1
    footfall_ratio: float | None = None     # recent 3-day mean / prior mean
    days_since_report: int | None = None


@dataclass(frozen=True)
class Reason:
    code: str
    points: int
    params: dict


@dataclass(frozen=True)
class FlagResult:
    score: int
    flagged: bool
    severity: str  # none | medium | high
    reasons: list[Reason]


def _pct(x: float) -> int:
    return round(x * 100)


def score_facility(m: FacilityMetrics) -> FlagResult:
    """Weighted 0-100 risk score; the reasons explain exactly where the points came from."""
    reasons: list[Reason] = []

    stock_pts = min(35, 12 * m.critical_stock + 5 * m.warning_stock)
    if m.critical_stock:
        reasons.append(Reason("stock_critical", stock_pts, {"count": m.critical_stock}))
    elif m.warning_stock:
        reasons.append(Reason("stock_warning", stock_pts, {"count": m.warning_stock}))

    if m.bed_occupancy is not None and m.bed_occupancy >= 0.85:
        pts = 20 if m.bed_occupancy >= 0.95 else 10
        reasons.append(Reason("beds_full", pts, {"pct": _pct(m.bed_occupancy)}))

    if m.attendance_rate is not None and m.attendance_rate < 0.75:
        pts = 25 if m.attendance_rate < 0.5 else 12
        reasons.append(Reason("low_attendance", pts, {"pct": _pct(m.attendance_rate)}))

    if m.test_availability is not None and m.test_availability < 0.75:
        pts = 15 if m.test_availability < 0.5 else 7
        reasons.append(Reason("low_tests", pts, {"pct": _pct(m.test_availability)}))

    if m.footfall_ratio is not None and m.footfall_ratio >= 1.5:
        reasons.append(Reason("footfall_surge", 10, {"pct": _pct(m.footfall_ratio - 1)}))

    if m.days_since_report is not None and m.days_since_report >= config.STALE_DATA_DAYS:
        reasons.append(Reason("stale_data", 10, {"days": m.days_since_report}))

    score = min(100, sum(r.points for r in reasons))
    flagged = score >= config.FLAG_THRESHOLD
    severity = "none"
    if flagged:
        severity = "high" if score >= config.HIGH_SEVERITY_THRESHOLD else "medium"
    return FlagResult(score, flagged, severity, sorted(reasons, key=lambda r: -r.points))
