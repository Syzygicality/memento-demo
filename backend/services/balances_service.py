"""Balance reads.

Balances are read straight from the materialized snapshot — an O(1) row fetch —
rather than summed from postings on every request. The snapshot's watermark
(``version`` / ``as_of_posting_id``) lets a caller that suspects staleness verify
against a live summation; ``recompute`` provides that authoritative fallback and
is used by the reconciliation job and by tests that assert the snapshot equals
the sum of postings.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from data.tables.balances import AccountBalance
from data.tables.transactions import Posting


async def current_balance(
    session: AsyncSession, tenant_id: str, account_id: uuid.UUID
) -> int | None:
    """Return the snapshot balance in minor units, or None if unknown."""
    snapshot = await session.get(AccountBalance, account_id)
    if snapshot is None or snapshot.tenant_id != tenant_id:
        return None
    return snapshot.balance


async def recompute(session: AsyncSession, account_id: uuid.UUID) -> int:
    """Authoritatively sum postings for an account (the slow, exact path)."""
    result = await session.execute(
        select(func.coalesce(func.sum(Posting.amount), 0)).where(
            Posting.account_id == account_id
        )
    )
    return int(result.scalar_one())
