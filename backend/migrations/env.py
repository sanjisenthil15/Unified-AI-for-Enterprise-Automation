"""
Alembic migration environment.

Wiring:
  - The database URL comes from backend/config/settings.py (which loads
    backend/.env), NOT from alembic.ini, so there is one source of truth.
  - target_metadata is Base.metadata with every ORM model imported via the
    `models` package, so `alembic revision --autogenerate` sees all tables.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# --------------------------------------------------------------------- #
# Make the backend package importable when Alembic runs from backend/.
# --------------------------------------------------------------------- #
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from config.database import Base          # noqa: E402
from config.settings import settings      # noqa: E402
import models                             # noqa: E402,F401  (registers all tables)

config = context.config

# Inject the runtime DATABASE_URL so alembic.ini stays credential-free.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (emits SQL)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live DB connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
