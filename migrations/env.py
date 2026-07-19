"""Alembic environment.

Pulls the DSN from the composed ``settings`` object rather than alembic.ini so
migrations and the app agree on where the database is, and imports every table
module (via ``register_models``) so ``--autogenerate`` sees the full metadata.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

from config.config import settings
from migrations import register_models  # noqa: F401 - imported for side effects

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.database.dsn)
target_metadata = SQLModel.metadata


def do_run_migrations(connection) -> None:  # type: ignore[no-untyped-def]
    """Run migrations within a single connection/transaction."""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and drive the migrations."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    context.configure(url=settings.database.dsn, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(run_async_migrations())
