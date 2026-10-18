"""Engine / session construction shared by the app, the CLI and Alembic."""
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from . import config


def make_engine(url: str | None = None) -> Engine:
    url = url or config.DATABASE_URL
    if url.startswith("sqlite"):
        kwargs: dict = {"connect_args": {"check_same_thread": False}}
        if url in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool  # one shared connection for in-memory DBs
        return create_engine(url, **kwargs)
    return create_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=10, pool_recycle=1800)


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(engine, expire_on_commit=False)
