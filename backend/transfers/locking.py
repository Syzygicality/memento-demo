"""Per-account serialization for transfers.

Concurrent transfers out of the same account must not both pass an
insufficient-funds check and overdraw it. The original design took a
``SELECT ... FOR UPDATE`` row lock on the source account for the length of the
transfer transaction; under contention that held the account row locked across
the whole posting write and serialized unrelated readers too.

This module replaces that with a Postgres **advisory lock** keyed by the account
id: it serializes writers to the same account without locking the row itself, so
balance reads stay live while a transfer is in flight (see DECISIONS.md →
transfer-advisory-lock, which superseded transfer-row-lock).
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _lock_key(account_id: uuid.UUID) -> int:
    """Map an account id to a stable 63-bit advisory-lock key."""
    return int.from_bytes(account_id.bytes[:8], "big") & 0x7FFF_FFFF_FFFF_FFFF


@asynccontextmanager
async def account_lock(
    session: AsyncSession, account_id: uuid.UUID
) -> AsyncIterator[None]:
    """Hold a transaction-scoped advisory lock on ``account_id``.

    The lock is released automatically when the surrounding transaction commits
    or rolls back (``pg_advisory_xact_lock``), so a crashed request never leaks a
    held lock.
    """
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:k)"), {"k": _lock_key(account_id)}
    )
    yield
