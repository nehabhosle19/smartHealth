"""Unit tests for the response builders and request helpers, without going through HTTP."""
from datetime import date, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker

from smarthealth import config, presenters
from smarthealth.db import make_engine
from smarthealth.models import Base, Footfall
from smarthealth.routers.reports import MAX_BACKDATE_DAYS, resolve_day, upsert
from smarthealth.seed import seed
from smarthealth.service import compute_district

TODAY = date(2026, 10, 18)


@pytest.fixture(scope="module")
def state_and_db():
    config.PBKDF2_ITERATIONS = 1000
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(engine)() as db:
        seed(db, TODAY, password="x" * 12)
        yield compute_district(db, TODAY), db


def test_footfall_series_is_ordered_complete_and_zero_filled(state_and_db):
    state, _ = state_and_db
    series = presenters.footfall_series(state, TODAY, days=20)
    days = [p["day"] for p in series]
    assert len(series) == 20 and days == sorted(days) and days[-1] == TODAY.isoformat()
    assert all(p["patients"] >= 0 for p in series)
    beyond_history = presenters.footfall_series(state, TODAY + timedelta(days=60), days=3)
    assert [p["patients"] for p in beyond_history] == [0, 0, 0]


def test_warning_rows_sorted_by_urgency_and_translated(state_and_db):
    state, _ = state_and_db
    english = presenters.warning_rows(state, "en")
    covers = [r["days_of_cover"] for r in english if r["days_of_cover"] is not None]
    assert english and covers == sorted(covers)
    assert all(r["level"] != "ok" for r in english)
    assert "stock left" in english[0]["message"]
    assert "स्टॉक" in presenters.warning_rows(state, "hi")[0]["message"]


def test_dashboard_summary_matches_facilities(state_and_db):
    state, _ = state_and_db
    dash = presenters.dashboard(state, TODAY, "en")
    summary, rows = dash["summary"], dash["facilities"]
    assert summary["facilities"] == len(rows) == 8
    assert summary["flagged"] == sum(r["flagged"] for r in rows)
    assert summary["beds_occupied"] == sum(r["beds_occupied"] for r in rows)
    assert [r["score"] for r in rows] == sorted((r["score"] for r in rows), reverse=True)


def test_transfer_rows_reference_known_facilities(state_and_db):
    state, _ = state_and_db
    rows = presenters.transfer_rows(state, "en")
    assert rows and all(r["source_id"] in state.facilities and r["target_id"] in state.facilities for r in rows)


def test_facility_overview_shape(state_and_db):
    state, _ = state_and_db
    fid = next(iter(state.facilities))
    overview = presenters.facility_overview(state, TODAY, fid, "en")
    assert set(overview) == {"facility", "beds", "stock", "tests", "footfall", "flag"}


# ---- request helpers ------------------------------------------------------------------------
def test_resolve_day_defaults_and_bounds():
    assert resolve_day(None, TODAY) == TODAY
    assert resolve_day(TODAY, TODAY) == TODAY
    oldest = TODAY - timedelta(days=MAX_BACKDATE_DAYS)
    assert resolve_day(oldest, TODAY) == oldest
    for bad in (TODAY + timedelta(days=1), oldest - timedelta(days=1)):
        with pytest.raises(HTTPException) as err:
            resolve_day(bad, TODAY)
        assert err.value.status_code == 422


def test_upsert_inserts_then_updates_single_row(state_and_db):
    _, db = state_and_db
    keys = {"facility_id": 1, "day": TODAY - timedelta(days=200)}
    upsert(db, Footfall, keys, {"patients": 10})
    upsert(db, Footfall, keys, {"patients": 99})
    db.flush()
    rows = db.query(Footfall).filter_by(**keys).all()
    assert len(rows) == 1 and rows[0].patients == 99
