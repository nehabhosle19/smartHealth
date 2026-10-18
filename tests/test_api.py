from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from smarthealth import config
from smarthealth.app import create_app
from smarthealth.seed import seed

PASSWORD = "test-password-123"
TODAY = date.today()


@pytest.fixture(scope="module")
def client():
    config.PBKDF2_ITERATIONS = 1000  # fast hashing for tests
    app = create_app("sqlite://", secret="test-secret", clock=lambda: TODAY)
    with app.state.session_factory() as db:
        seed(db, TODAY, password=PASSWORD)
    with TestClient(app) as c:
        yield c


def login(client, username, password=PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def auth(client, username):
    r = login(client, username)
    assert r.status_code == 200
    client.cookies.clear()  # tests authenticate per-request with Bearer headers
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def admin(client):
    return auth(client, "admin")


@pytest.fixture(scope="module")
def staff1(client):
    return auth(client, "staff1")


# ---- authentication / authorisation ------------------------------------------------
def test_login_failure_is_generic(client):
    a = login(client, "admin", "nope")
    b = login(client, "ghost", "nope")
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_endpoints_require_auth(client):
    for path in ["/api/facilities", "/api/district/dashboard", "/api/medicines"]:
        assert client.get(path).status_code == 401
    assert client.get("/api/facilities",
                      headers={"Authorization": "Bearer junk"}).status_code == 401


def test_staff_cannot_use_district_endpoints(client, staff1):
    for path in ["dashboard", "flags", "redistribution", "stockout-warnings"]:
        assert client.get(f"/api/district/{path}", headers=staff1).status_code == 403


def test_staff_limited_to_own_facility(client, staff1):
    assert len(client.get("/api/facilities", headers=staff1).json()) == 1
    assert client.get("/api/facilities/1/overview", headers=staff1).status_code == 200
    assert client.get("/api/facilities/2/overview", headers=staff1).status_code == 403
    r = client.post("/api/facilities/2/footfall", json={"patients": 5}, headers=staff1)
    assert r.status_code == 403


def test_admin_can_access_any_facility_and_404s_unknown(client, admin):
    assert client.get("/api/facilities/2/overview", headers=admin).status_code == 200
    assert client.get("/api/facilities/999/overview", headers=admin).status_code == 404


def test_login_throttling(client):
    app_client = TestClient(create_app("sqlite://", secret="s"))
    for _ in range(5):
        assert login(app_client, "victim", "bad").status_code == 401
    assert login(app_client, "victim", "bad").status_code == 429


def test_security_headers_present(client):
    r = client.get("/api/facilities")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]


# ---- validation -----------------------------------------------------------------------
@pytest.mark.parametrize("path,body", [
    ("stock", {"medicine_id": 1, "closing_qty": -1, "consumed": 0}),
    ("stock", {"medicine_id": 1, "closing_qty": 1, "consumed": 0, "extra": 1}),
    ("stock", {"medicine_id": 1, "closing_qty": 1, "consumed": 0,
               "day": (TODAY + timedelta(days=1)).isoformat()}),
    ("footfall", {"patients": 10**9}),
    ("beds", {"total": 5, "occupied": 6}),
    ("attendance", {"doctor_name": "", "present": True}),
    ("tests", {"test_name": "x" * 500, "available": True}),
])
def test_invalid_input_rejected(client, staff1, path, body):
    assert client.post(f"/api/facilities/1/{path}", json=body, headers=staff1).status_code == 422


def test_unknown_medicine_rejected(client, staff1):
    r = client.post("/api/facilities/1/stock", headers=staff1,
                    json={"medicine_id": 9999, "closing_qty": 1, "consumed": 1})
    assert r.status_code == 404


# ---- behaviour ------------------------------------------------------------------------
def test_report_is_upsert_and_visible(client, staff1):
    for occupied in (3, 4):
        r = client.post("/api/facilities/1/beds", json={"total": 30, "occupied": occupied},
                        headers=staff1)
        assert r.status_code == 201
    beds = client.get("/api/facilities/1/overview", headers=staff1).json()["beds"]
    assert beds == {"total": 30, "occupied": 4}


def test_dashboard_flags_the_engineered_problem_facilities(client, admin):
    d = client.get("/api/district/dashboard", headers=admin).json()
    assert d["summary"]["facilities"] == 8 and d["summary"]["flagged"] >= 1
    flagged = {f["name"] for f in d["facilities"] if f["flagged"]}
    assert {"PHC Aliganj", "PHC Gosainganj"} <= flagged  # low attendance / tests / stock
    assert "CHC Rampur" not in flagged
    scores = [f["score"] for f in d["facilities"]]
    assert scores == sorted(scores, reverse=True)


def test_early_stockout_warnings(client, admin):
    w = client.get("/api/district/stockout-warnings", headers=admin).json()
    assert w and all(x["level"] in ("critical", "warning") for x in w)
    covers = [x["days_of_cover"] for x in w if x["days_of_cover"] is not None]
    assert covers == sorted(covers)
    assert any(x["facility"] == "PHC Gosainganj" for x in w)


def test_redistribution_moves_from_overstocked_to_short(client, admin):
    plan = client.get("/api/district/redistribution", headers=admin).json()
    assert plan
    short = {x["facility"] for x in client.get("/api/district/stockout-warnings",
                                               headers=admin).json()}
    assert all(p["target"] in short for p in plan)
    assert all(p["source"] in {"CHC Rampur", "CHC Malihabad"} for p in plan)
    assert all(p["quantity"] > 0 and p["source"] != p["target"] for p in plan)


def test_forecast_endpoint(client, admin):
    r = client.get("/api/facilities/1/forecast?medicine_id=1&days=10", headers=admin)
    body = r.json()
    assert r.status_code == 200 and len(body["forecast"]) == 10 and body["history"]
    assert client.get("/api/facilities/1/forecast?medicine_id=1&days=0",
                      headers=admin).status_code == 422
    assert client.get("/api/facilities/1/forecast?medicine_id=999",
                      headers=admin).status_code == 404


@pytest.mark.parametrize("lang,needle", [("hi", "डॉक्टर"), ("ta", "மருத்துவர்"), ("en", "Doctor")])
def test_multilingual_flag_messages(client, admin, lang, needle):
    flags = client.get(f"/api/district/flags?lang={lang}", headers=admin).json()
    text = " ".join(r["message"] for f in flags for r in f["reasons"])
    assert needle in text


def test_accept_language_header_and_fallback(client, admin):
    hi = client.get("/api/district/flags", headers={**admin, "Accept-Language": "hi-IN,en;q=0.5"})
    assert "डॉक्टर" in hi.text
    fr = client.get("/api/district/flags?lang=fr", headers=admin)  # unsupported -> English
    assert "Doctor" in fr.text


def test_footfall_trend_and_missing_tests(client, admin):
    d = client.get("/api/district/dashboard", headers=admin).json()
    assert len(d["footfall_trend"]) == 14
    assert d["footfall_trend"][-1]["day"] == TODAY.isoformat()
    assert all(p["patients"] > 0 for p in d["footfall_trend"])
    by_name = {f["name"]: f for f in d["facilities"]}
    assert "Hemoglobin" in by_name["PHC Aliganj"]["missing_tests"]
    assert by_name["CHC Rampur"]["missing_tests"] == []


def test_facility_overview_has_tests_and_footfall(client, staff1):
    o = client.get("/api/facilities/1/overview", headers=staff1).json()
    assert len(o["footfall"]) == 14 and len(o["tests"]) == 5
    assert all(set(t) == {"name", "available"} for t in o["tests"])


# ---- production hardening ------------------------------------------------------------
def test_health_is_public_and_minimal(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_oversized_body_rejected(client, staff1):
    r = client.post("/api/facilities/1/footfall", headers=staff1,
                    content=b"{" + b" " * 70_000 + b"}")
    assert r.status_code == 413


def test_cookie_session_requires_csrf_header_for_writes(client):
    r = login(client, "staff1")
    assert r.status_code == 200
    set_cookie = r.headers["set-cookie"].lower()
    assert "httponly" in set_cookie and "samesite=strict" in set_cookie
    try:
        assert client.get("/api/facilities").status_code == 200           # reads: cookie suffices
        no_header = client.post("/api/facilities/1/footfall", json={"patients": 5})
        assert no_header.status_code == 403                                 # cross-site style write
        ok = client.post("/api/facilities/1/footfall", json={"patients": 5},
                         headers={"X-Requested-With": "smarthealth"})
        assert ok.status_code == 201
        assert client.post("/api/auth/logout").status_code == 204
        assert client.get("/api/facilities").status_code == 401             # cookie cleared
    finally:
        client.cookies.clear()


def test_deactivated_user_and_password_change_revoke_tokens(client):
    from sqlalchemy import select

    from smarthealth.manage import set_active, set_password
    from smarthealth.models import User

    headers = auth(client, "staff3")
    assert client.get("/api/facilities", headers=headers).status_code == 200
    with client.app.state.session_factory() as db:
        set_password(db, "staff3", "Brand-New-Passw0rd")
    assert client.get("/api/facilities", headers=headers).status_code == 401  # old token dead
    assert login(client, "staff3").status_code == 401                         # old password dead
    fresh = login(client, "staff3", "Brand-New-Passw0rd")
    assert fresh.status_code == 200
    client.cookies.clear()
    with client.app.state.session_factory() as db:
        set_active(db, "staff3", False)
        assert db.scalar(select(User.is_active).where(User.username == "staff3")) is False
    bearer = {"Authorization": f"Bearer {fresh.json()['token']}"}
    assert client.get("/api/facilities", headers=bearer).status_code == 401
    assert login(client, "staff3", "Brand-New-Passw0rd").status_code == 401


def test_backdating_limits(client, staff1):
    too_old = (TODAY - timedelta(days=500)).isoformat()
    r = client.post("/api/facilities/1/footfall", json={"patients": 5, "day": too_old}, headers=staff1)
    assert r.status_code == 422
    yesterday = (TODAY - timedelta(days=1)).isoformat()
    r = client.post("/api/facilities/1/footfall", json={"patients": 5, "day": yesterday}, headers=staff1)
    assert r.status_code == 201
