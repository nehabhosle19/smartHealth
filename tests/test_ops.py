"""Configuration and management-CLI tests."""
import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from smarthealth import config, manage
from smarthealth.db import make_engine
from smarthealth.models import Base, Facility, User
from smarthealth.security import verify_password


@pytest.fixture()
def db():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(engine)() as session:
        yield session


def test_production_config_rejects_unsafe_settings():
    good = "x" * 40
    assert config.production_problems(good, True, True) == []
    assert config.production_problems(good, False, True)           # random per-process key
    assert config.production_problems("short", True, True)         # too short
    assert config.production_problems(good, True, False)           # cookies not Secure


def test_database_url_normalisation(monkeypatch):
    import importlib

    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@h:5432/db")
    monkeypatch.delenv("SMARTHEALTH_DB", raising=False)
    try:
        assert importlib.reload(config).DATABASE_URL == "postgresql+psycopg://u:p@h:5432/db"
    finally:
        monkeypatch.undo()
        importlib.reload(config)


@pytest.mark.parametrize("pw", ["short1A", "alllowercase123", "ALLUPPERCASE123", "NoDigitsHereAtAll"])
def test_weak_passwords_rejected(db, pw):
    with pytest.raises(manage.CliError):
        manage.create_admin(db, "district.admin", pw)


def test_create_admin_and_staff(db, monkeypatch):
    monkeypatch.setattr(config, "PBKDF2_ITERATIONS", 1000)
    admin = manage.create_admin(db, "district.admin", "Str0ng-Passphrase")
    assert admin.role == "admin" and verify_password("Str0ng-Passphrase", admin.password_hash)
    with pytest.raises(manage.CliError):
        manage.create_admin(db, "district.admin", "Str0ng-Passphrase")      # duplicate
    with pytest.raises(manage.CliError):
        manage.create_staff(db, "staff.one", "Str0ng-Passphrase", 99)       # no such facility
    f = manage.add_facility(db, "PHC Test", "PHC", "D", 26.0, 80.0)
    staff = manage.create_staff(db, "staff.one", "Str0ng-Passphrase", f.id)
    assert (staff.role, staff.facility_id) == ("staff", f.id)


@pytest.mark.parametrize("name", ["a", "bad name", "x" * 65, "semi;colon"])
def test_bad_usernames_rejected(db, name):
    with pytest.raises(manage.CliError):
        manage.create_admin(db, name, "Str0ng-Passphrase")


def test_facility_validation(db):
    with pytest.raises(manage.CliError):
        manage.add_facility(db, "X", "HOSPITAL", "D", 0, 0)
    with pytest.raises(manage.CliError):
        manage.add_facility(db, "X", "PHC", "D", 123, 0)
    manage.add_facility(db, "X", "PHC", "D", 10, 10)
    with pytest.raises(manage.CliError):
        manage.add_facility(db, "X", "CHC", "D", 10, 10)                    # duplicate name
    assert db.scalar(select(Facility).where(Facility.name == "X")) is not None


def test_cli_refuses_demo_seed_in_production(monkeypatch, capsys):
    monkeypatch.setattr(config, "IS_PROD", True)
    assert manage.main(["seed-demo"]) == 1
    assert "refusing" in capsys.readouterr().err


def test_set_password_revokes_by_changing_hash(db, monkeypatch):
    monkeypatch.setattr(config, "PBKDF2_ITERATIONS", 1000)
    u = manage.create_admin(db, "district.admin", "Str0ng-Passphrase")
    before = u.password_hash[-16:]
    manage.set_password(db, "district.admin", "An0ther-Passphrase")
    assert db.scalar(select(User.password_hash)).endswith(before) is False
