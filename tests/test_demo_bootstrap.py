"""bootstrap-demo: lets a host without shell access (free Render) create/refresh the demo from env vars."""
from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from smarthealth import config, manage
from smarthealth.db import make_engine, make_session_factory
from smarthealth.models import Base, Facility, StockLog, User
from smarthealth.security import verify_password
from smarthealth.seed import bootstrap_demo

TODAY = date(2026, 10, 18)


@pytest.fixture(autouse=True)
def fast_hashing(monkeypatch):
    monkeypatch.setattr(config, "PBKDF2_ITERATIONS", 1000)


@pytest.fixture()
def db(tmp_path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'demo.db').as_posix()}")
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as session:
        yield session


def password_works(db, username: str, password: str) -> bool:
    user = db.scalar(select(User).where(User.username == username))
    return verify_password(password, user.password_hash)


def test_empty_database_gets_a_full_demo_district(db):
    assert "created" in bootstrap_demo(db, TODAY, "Demo-Pass-1")
    assert db.scalar(select(func.count(Facility.id))) == 8
    assert all(password_works(db, name, "Demo-Pass-1") for name in ("admin", "staff1", "staff8"))
    assert db.scalar(select(func.max(StockLog.day))) == TODAY


def test_running_twice_with_same_password_changes_nothing(db):
    bootstrap_demo(db, TODAY, "Demo-Pass-1")
    before = db.scalar(select(func.count(StockLog.id)))
    assert "current; 0 password(s) updated" in bootstrap_demo(db, TODAY, "Demo-Pass-1")
    assert db.scalar(select(func.count(StockLog.id))) == before


def test_changing_the_env_password_updates_all_demo_accounts(db):
    bootstrap_demo(db, TODAY, "Demo-Pass-1")
    assert "9 password(s) updated" in bootstrap_demo(db, TODAY, "Another-Pass-2")
    assert password_works(db, "admin", "Another-Pass-2")
    assert not password_works(db, "admin", "Demo-Pass-1")


def test_real_accounts_are_never_touched_by_a_password_sync(db):
    bootstrap_demo(db, TODAY, "Demo-Pass-1")
    manage.create_admin(db, "real.person", "Real-Passw0rd-xy")
    bootstrap_demo(db, TODAY, "Another-Pass-2")
    assert password_works(db, "real.person", "Real-Passw0rd-xy")


def test_stale_demo_data_is_regenerated_so_dashboards_stay_fresh(db):
    bootstrap_demo(db, TODAY, "Demo-Pass-1")
    later = TODAY + timedelta(days=5)
    assert "created" in bootstrap_demo(db, later, "Demo-Pass-1")
    assert db.scalar(select(func.max(StockLog.day))) == later
    assert db.scalar(select(func.count(Facility.id))) == 8  # replaced, not duplicated


def test_cli_requires_password_and_refuses_production(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "DATABASE_URL", f"sqlite:///{(tmp_path / 'cli.db').as_posix()}")
    monkeypatch.delenv("SMARTHEALTH_DEMO_PASSWORD", raising=False)
    assert manage.main(["bootstrap-demo"]) == 1
    assert "SMARTHEALTH_DEMO_PASSWORD" in capsys.readouterr().err

    monkeypatch.setenv("SMARTHEALTH_DEMO_PASSWORD", "Demo-Pass-1")
    assert manage.main(["bootstrap-demo"]) == 0
    assert "created" in capsys.readouterr().out

    monkeypatch.setattr(config, "IS_PROD", True)
    assert manage.main(["bootstrap-demo"]) == 1
    assert "refusing" in capsys.readouterr().err
