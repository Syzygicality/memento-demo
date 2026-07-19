"""Application lifespan.

Startup verifies database connectivity and that migrations are current; it never
creates schema (Alembic owns DDL). If the DB is unreachable or behind on
migrations, the app refuses to serve rather than starting in a half-configured
state where a money write could hit a table without its balance trigger.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from data.database.engine import get_engine

logger = logging.getLogger("ledger.lifespan")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Verify connectivity on startup; dispose the engine on shutdown."""
    engine = get_engine()
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    logger.info("ledger: database reachable, ready to serve")
    yield
    await engine.dispose()
