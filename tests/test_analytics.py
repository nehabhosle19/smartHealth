import pytest

from smarthealth import analytics as an
from smarthealth.analytics import FacilityMetrics, StockPosition


# ---- forecasting ---------------------------------------------------------------
def test_forecast_flat_series_stays_flat():
    f = an.holt_forecast([10.0] * 20, 7)
    assert all(v == pytest.approx(10, abs=0.01) for v in f)


def test_forecast_follows_rising_trend_but_is_damped():
    f = an.holt_forecast([float(10 + 2 * i) for i in range(20)], 30)
    assert f[0] > 45 and f[-1] > f[0]  # series mean is 29; forecast tracks the ramp
    assert f[-1] - f[0] < 2 * 30  # damped: less than undamped linear extrapolation


def test_forecast_never_negative_and_handles_short_input():
    assert min(an.holt_forecast([20, 10, 5, 1, 0], 14)) >= 0
    assert an.holt_forecast([], 3) == [0.0] * 3
    assert an.holt_forecast([4.0, 6.0], 2) == [5.0, 5.0]
    assert an.holt_forecast([1.0], 0) == []


# ---- stock assessment ----------------------------------------------------------
@pytest.mark.parametrize("on_hand,level", [(0, "critical"), (20, "critical"), (50, "warning"),
                                           (500, "ok")])
def test_assess_levels(on_hand, level):
    a = an.assess_stock(on_hand, [10.0] * 14)  # 10/day
    assert a.level == level


def test_assess_zero_demand_is_ok_with_no_cover_figure():
    a = an.assess_stock(5, [0.0] * 10)
    assert (a.level, a.days_of_cover, a.reorder_qty) == ("ok", None, 0)


def test_reorder_tops_up_to_target_cover():
    a = an.assess_stock(30, [10.0] * 14)
    assert a.reorder_qty == 110  # 14 days * 10 - 30


# ---- redistribution ----------------------------------------------------------------
def pos(fid, on_hand, demand, lat=26.0, lon=80.0, med=1):
    return StockPosition(fid, med, on_hand, demand, lat, lon)


def test_haversine_known_distance():
    assert an.haversine_km(0, 0, 0, 1) == pytest.approx(111.2, abs=0.5)
    assert an.haversine_km(10, 10, 10, 10) == 0


def test_transfer_from_surplus_to_deficit():
    t = an.plan_transfers([pos(1, 5, 10), pos(2, 1000, 10)])
    assert len(t) == 1 and (t[0].source_id, t[0].target_id) == (2, 1)
    assert t[0].quantity == 135  # 14d*10 - 5


def test_donor_keeps_reserve_and_total_never_exceeds_surplus():
    positions = [pos(1, 0, 10), pos(2, 0, 10), pos(3, 400, 10)]  # donor spare = 400-210 = 190
    transfers = an.plan_transfers(positions)
    assert sum(x.quantity for x in transfers) <= 190
    assert all(x.source_id == 3 for x in transfers)


def test_most_urgent_deficit_served_first_and_nearest_donor_preferred():
    positions = [
        pos(1, 5, 10, lat=26.0), pos(2, 60, 10, lat=26.0),     # 1 is more urgent than 2
        pos(3, 400, 10, lat=26.1), pos(4, 400, 10, lat=28.0),  # 3 is nearer
    ]
    transfers = an.plan_transfers(positions)
    assert transfers[0].target_id == 1 and transfers[0].source_id == 3


def test_no_transfers_when_nobody_has_surplus_or_deficit():
    assert an.plan_transfers([pos(1, 100, 10), pos(2, 120, 10)]) == []
    assert an.plan_transfers([pos(1, 0, 10)]) == []


def test_medicines_are_not_mixed():
    t = an.plan_transfers([pos(1, 0, 10, med=1), pos(2, 1000, 10, med=2)])
    assert t == []


# ---- facility scoring -------------------------------------------------------------
def test_healthy_facility_not_flagged():
    r = an.score_facility(FacilityMetrics(0, 0, 0.5, 0.95, 1.0, 1.0, 0))
    assert (r.score, r.flagged, r.severity, r.reasons) == (0, False, "none", [])


def test_unknown_metrics_do_not_penalise():
    assert an.score_facility(FacilityMetrics()).score == 0


def test_underperforming_facility_is_flagged_with_explanations():
    r = an.score_facility(FacilityMetrics(critical_stock=2, bed_occupancy=1.0,
                                          attendance_rate=0.3, test_availability=0.4))
    assert r.flagged and r.severity == "high"
    assert [x.code for x in r.reasons][0] == "low_attendance"  # biggest contributor first
    assert {"stock_critical", "beds_full", "low_tests"} <= {x.code for x in r.reasons}


def test_score_capped_at_100_and_threshold_boundary():
    worst = FacilityMetrics(5, 5, 1.0, 0.0, 0.0, 3.0, 30)
    assert an.score_facility(worst).score == 100
    # exactly 40 points -> flagged (25 attendance + 15 tests)
    r = an.score_facility(FacilityMetrics(attendance_rate=0.4, test_availability=0.4))
    assert r.score == 40 and r.flagged and r.severity == "medium"
