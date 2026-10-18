"""Alembic environment: uses the same database URL and models as the application."""
from logging.config import fileConfig

from alembic import context

from smarthealth import config as app_config
from smarthealth.db import make_engine
from smarthealth.models import Base

alembic_cfg = context.config
if alembic_cfg.config_file_name:
    fileConfig(alembic_cfg.config_file_name)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=app_config.DATABASE_URL, target_metadata=target_metadata,
                      literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = make_engine()
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata,
                          compare_type=True, render_as_batch=connection.dialect.name == "sqlite")
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
