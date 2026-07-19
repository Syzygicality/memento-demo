"""Async engine and session factory.

The engine is created lazily and `get_db_session` is the single accessor every
repository calls *per operation* — it is never cached by a wrapper — because the
test harness monkeypatches this function to point at a fresh per-test Postgres
database. A wrapper that captured the engine once would bypass that swap and hit
the wrong DB (see DECISIONS.md → repository-reresolves-session).

The application creates no schema here: Alembic owns all DDL. Startup only
verifies connectivity (see api/lifespan.py).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config.config import settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return the process-wide async engine, creating it on first use."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database.dsn,
            pool_size=settings.database.pool_size,
            max_overflow=settings.database.max_overflow,
            pool_pre_ping=True,
        )
    return _engine


def _get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            get_engine(), expire_on_commit=False, autoflush=False
        )
    return _sessionmaker


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Yield a session. Re-resolved per call; monkeypatched in tests."""
    async with _get_sessionmaker()() as session:
        yield session
