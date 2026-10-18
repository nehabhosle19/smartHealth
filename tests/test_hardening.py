"""Middleware, production-config, health, CLI and concurrency edge cases."""
import re
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError

from smarthealth import config, manage
from smarthealth.app import create_app
from smarthealth.db import make_engine, make_session_factory
from smarthealth.i18n import DEFAULT_LANG, MESSAGES, resolve_lang, t
from smarthealth.models import Base, Facility, Footfall
from smarthealth.routers.reports import upsert

TODAY = date(2026, 10, 18)


# ---- middleware / app factory ------------------------------------------------------------
def test_hsts_only_sent_when_cookies_are_secure(monkeypatch):
    with TestClient(create_app("sqlite://", secret="s")) as client:
        assert "strict-transport-security" not in client.get("/api/health").headers
    monkeypatch.setattr(config, "COOKIE_SECURE", True)
    with TestClient(create_app("sqlite://", secret="s")) as client:
        assert "max-age=" in client.get("/api/health").headers["strict-transport-security"]


def test_static_assets_are_revalidated_but_api_is_never_cached():
    with TestClient(create_app("sqlite://", secret="s")) as client:
        assert client.get("/api/health").headers["cache-control"] == "no-store"
        assert client.get("/").headers["cache-control"] == "no-cache"


def test_malformed_content_length_is_rejected():
    with TestClient(create_app("sqlite://", secret="s")) as client:
        response = client.post("/api/auth/login", content=b"{}", headers={"content-length": "abc"})
        assert response.status_code in (400, 413)


def test_host_header_is_validated_when_configured(monkeypatch):
    monkeypatch.setattr(config, "ALLOWED_HOSTS", ["good.example"])
    app = create_app("sqlite://", secret="s")
    assert TestClient(app, base_url="http://good.example").get("/api/health").status_code == 200
    assert TestClient(app, base_url="http://evil.example").get("/api/health").status_code == 400


def test_production_refuses_to_start_with_unsafe_config(monkeypatch):
    monkeypatch.setattr(config, "IS_PROD", True)
    monkeypatch.setattr(config, "COOKIE_SECURE", False)
    with pytest.raises(RuntimeError, match="Unsafe production configuration"):
        create_app("sqlite://", secret="x" * 40)
    monkeypatch.setattr(config, "COOKIE_SECURE", True)
    with pytest.raises(RuntimeError, match="SMARTHEALTH_SECRET"):
        create_app("sqlite://")  # random per-process key is not acceptable in production
    assert create_app("sqlite://", secret="x" * 40)  # safe settings start fine


def test_health_reports_503_when_database_is_down():
    app = create_app("sqlite://", secret="s")

    def broken_factory():
        raise RuntimeError("database unreachable")

    app.state.session_factory = broken_factory
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 503 and response.json() == {"status": "unavailable"}


# ---- concurrency: two first-writers racing on the same row ----------------------------------
@pytest.fixture()
def db():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as session:
        session.add(Facility(name="F", type="PHC", district="D", lat=1, lon=1))
        session.commit()
        yield session


def test_upsert_recovers_when_another_writer_inserts_first(db, monkeypatch):
    keys = {"facility_id": 1, "day": TODAY}
    real_begin_nested = db.begin_nested

    class LostRace:
        """Simulates: our SELECT found nothing, then a concurrent request inserted the row."""

        def __enter__(self):
            db.execute(insert(Footfall).values(**keys, patients=1))
            raise IntegrityError("INSERT", {}, Exception("unique constraint"))

        def __exit__(self, *exc):
            return False

    calls = iter([LostRace()])
    monkeypatch.setattr(db, "begin_nested", lambda: next(calls, None) or real_begin_nested())
    upsert(db, Footfall, keys, {"patients": 99})
    rows = db.scalars(select(Footfall)).all()
    assert len(rows) == 1 and rows[0].patients == 99


def test_upsert_gives_up_after_second_integrity_error(db, monkeypatch):
    class AlwaysFails:
        def __enter__(self):
            raise IntegrityError("INSERT", {}, Exception("unique constraint"))

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(db, "begin_nested", lambda: AlwaysFails())
    with pytest.raises(IntegrityError):
        upsert(db, Footfall, {"facility_id": 1, "day": TODAY}, {"patients": 5})


# ---- management CLI end to end -------------------------------------------------------------------
@pytest.fixture()
def cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "DATABASE_URL", f"sqlite:///{(tmp_path / 'cli.db').as_posix()}")
    monkeypatch.setattr(config, "PBKDF2_ITERATIONS", 1000)
    monkeypatch.setenv("SMARTHEALTH_PASSWORD", "Cli-Passw0rd-ok")

    def run(*argv) -> tuple[int, str, str]:
        code = manage.main(list(argv))
        out = capsys.readouterr()
        return code, out.out, out.err

    run("init-db")
    return run


def test_cli_bootstraps_a_deployment(cli):
    assert cli("add-facility", "--name", "PHC One", "--type", "PHC", "--district", "D",
               "--lat", "26.5", "--lon", "80.5")[:2] == (0, "facility created with id 1\n")
    assert cli("add-medicine", "--name", "Paracetamol", "--unit", "tablets")[0] == 0
    assert cli("create-admin", "--username", "boss.user")[1] == "admin created\n"
    assert cli("create-staff", "--username", "staff.one", "--facility-id", "1")[1] == "staff user created\n"
    assert "PHC One" in cli("list-facilities")[1]
    assert cli("deactivate", "--username", "staff.one")[1] == "user deactivated\n"
    assert cli("activate", "--username", "staff.one")[1] == "user activated\n"
    assert "sessions revoked" in cli("set-password", "--username", "staff.one")[1]


def test_cli_reports_errors_without_a_traceback(cli):
    code, _, err = cli("create-staff", "--username", "staff.one", "--facility-id", "99")
    assert code == 1 and "does not exist" in err
    assert cli("deactivate", "--username", "nobody.here")[0] == 1
    assert cli("add-facility", "--name", "X", "--type", "PHC", "--district", "D",
               "--lat", "999", "--lon", "0")[0] == 1
    cli("add-medicine", "--name", "M", "--unit", "u")
    assert "already exists" in cli("add-medicine", "--name", "M", "--unit", "u")[2]


def test_cli_seed_demo_loads_data_once(cli):
    code, out, _ = cli("seed-demo")
    assert code == 0 and "admin" in out
    with pytest.raises(RuntimeError, match="already contains data"):
        cli("seed-demo")


# ---- translations stay in sync -----------------------------------------------------------------
def _placeholders(template: str) -> set[str]:
    return set(re.findall(r"{(\w+)}", template))


def test_every_language_has_every_message_with_the_same_placeholders():
    english = MESSAGES[DEFAULT_LANG]
    for lang, catalogue in MESSAGES.items():
        assert catalogue.keys() == english.keys(), f"{lang} is missing or has extra keys"
        for key, template in catalogue.items():
            assert _placeholders(template) == _placeholders(english[key]), f"{lang}.{key} placeholders differ"


def test_language_resolution():
    assert resolve_lang("hi-IN,en;q=0.8") == "hi"
    assert resolve_lang("fr, ta;q=0.5") == "ta"
    assert resolve_lang("fr") == resolve_lang(None) == resolve_lang("") == DEFAULT_LANG
    assert t("xx", "level_ok") == t("en", "level_ok")  # unknown language falls back to English


# ---- deployment files ------------------------------------------------------------------------
def test_container_scripts_use_unix_line_endings():
    """A CRLF shebang (`#!/bin/sh\r`) makes Linux containers fail with 'no such file or directory'."""
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    for name in ("docker-entrypoint.sh", "Dockerfile"):
        assert b"\r" not in (root / name).read_bytes(), f"{name} contains CRLF line endings"
    assert "*.sh text eol=lf" in (root / ".gitattributes").read_text()
