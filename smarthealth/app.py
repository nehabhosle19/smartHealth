"""Application factory: wires configuration, database, middleware and routers together."""
from __future__ import annotations

import logging
import mimetypes
from collections.abc import Callable
from datetime import date
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles

from . import config, middleware
from .db import make_engine, make_session_factory
from .models import Base
from .routers import auth, district, facilities, health, reports
from .security import LoginThrottle

# ES modules are rejected by browsers unless served as JavaScript; some systems map .js to text/plain.
mimetypes.add_type("text/javascript", ".js")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
log = logging.getLogger("smarthealth")

LOGIN_FAILURES_PER_USER = 5
LOGIN_FAILURES_PER_IP = 30
LOGIN_WINDOW_SECONDS = 300


def _check_production_config(secret: str | None) -> None:
    """Refuse to start in production with unsafe settings instead of silently degrading."""
    problems = config.production_problems(
        secret or config.SECRET_KEY, bool(secret) or config.SECRET_FROM_ENV, config.COOKIE_SECURE
    )
    if problems:
        raise RuntimeError("Unsafe production configuration:\n - " + "\n - ".join(problems))
    if not config.ALLOWED_HOSTS:
        log.warning("SMARTHEALTH_ALLOWED_HOSTS is not set; Host header is not validated")


def _api_router() -> APIRouter:
    api = APIRouter(prefix="/api")
    for module in (health, auth, facilities, reports, district):
        api.include_router(module.router)
    return api


def create_app(
    database_url: str | None = None,
    secret: str | None = None,
    clock: Callable[[], date] = config.local_today,
) -> FastAPI:
    if not logging.getLogger().handlers:
        logging.basicConfig(level=config.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if config.IS_PROD:
        _check_production_config(secret)

    engine = make_engine(database_url)
    if not config.IS_PROD:  # production schemas are managed by `alembic upgrade head`
        Base.metadata.create_all(engine)

    app = FastAPI(title="Smart Health", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.secret = secret or config.SECRET_KEY
    app.state.clock = clock
    app.state.user_throttle = LoginThrottle(LOGIN_FAILURES_PER_USER, LOGIN_WINDOW_SECONDS)
    app.state.ip_throttle = LoginThrottle(LOGIN_FAILURES_PER_IP, LOGIN_WINDOW_SECONDS)

    middleware.install(app)
    app.include_router(_api_router())
    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app
