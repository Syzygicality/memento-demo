"""Repository base.

Every table accessor extends this and obtains its session by *calling*
``get_db_session`` each time rather than caching an engine or session, so the
per-test DB swap in the harness always takes effect. Repositories never open
their own transactions for money mutations: the service layer owns the
transaction boundary so a transfer's posting and its idempotency record commit
together (see DECISIONS.md → idempotency-same-transaction).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from data.database.engine import get_db_session


class BaseRepository:
    """Session-per-call base for all table accessors."""

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield a fresh session for a single read.

        For writes that must be atomic with other writes, the caller passes an
        already-open session instead of using this helper.
        """
        agen = get_db_session()
        session = await agen.__anext__()
        try:
            yield session
        finally:
            await agen.aclose()
