"""Balance reads.

Balances are read straight from the materialized snapshot — an O(1) row fetch —
rather than summed from postings on every request. The snapshot's watermark
(``version`` / ``as_of_posting_id``) lets a caller that suspects staleness verify
against a live summation; ``recompute`` provides that authoritative fallback and
is used by the reconciliation job and by tests that assert the snapshot equals
the sum of postings.

A balance now has two figures: the **posted** balance (the snapshot, money that
has actually settled) and the **available** balance (posted minus funds reserved
by active, unexpired holds). ``available`` is what a funds check must consult, so
a hold that has reserved money cannot be spent twice (see DECISIONS.md →
available-vs-posted-split). The held total is summed live at read time with the
DB clock deciding expiry, so an expired hold stops reducing available with no
sweep required (see DECISIONS.md → hold-expiry-frees-on-read).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from data.tables.balances import AccountBalance
from data.tables.holds import Hold, HoldState
from data.tables.transactions import Posting


@dataclass(frozen=True)
class Balance:
    """An account's posted balance and its available (spendable) balance."""

    posted: int
    held: int

    @property
    def available(self) -> int:
        """Posted minus funds reserved by active, unexpired holds."""
        return self.posted - self.held


async def current_balance(
    session: AsyncSession, tenant_id: str, account_id: uuid.UUID
) -> int | None:
    """Return the snapshot (posted) balance in minor units, or None if unknown."""
    snapshot = await session.get(AccountBalance, account_id)
    if snapshot is None or snapshot.tenant_id != tenant_id:
        return None
    return snapshot.balance


async def held_total(
    session: AsyncSession, tenant_id: str, account_id: uuid.UUID
) -> int:
    """Sum funds reserved by this account's active, unexpired holds.

    Expiry is judged by the database clock (``func.now()``) so a hold past its
    ``expires_at`` stops counting immediately, without waiting for a sweep to
    move it out of the ``ACTIVE`` state.
    """
    result = await session.execute(
        select(func.coalesce(func.sum(Hold.amount), 0)).where(
            Hold.account_id == account_id,
            Hold.tenant_id == tenant_id,
            Hold.state == HoldState.ACTIVE,
            Hold.expires_at > func.now(),
        )
    )
    return int(result.scalar_one())


async def available_balance(
    session: AsyncSession, tenant_id: str, account_id: uuid.UUID
) -> Balance | None:
    """Return the posted and available balances, or None if the account is unknown.

    This is the figure a funds check consults: ``available`` already subtracts
    everything reserved by outstanding holds.
    """
    posted = await current_balance(session, tenant_id, account_id)
    if posted is None:
        return None
    held = await held_total(session, tenant_id, account_id)
    return Balance(posted=posted, held=held)


async def recompute(session: AsyncSession, account_id: uuid.UUID) -> int:
    """Authoritatively sum postings for an account (the slow, exact path)."""
    result = await session.execute(
        select(func.coalesce(func.sum(Posting.amount), 0)).where(
            Posting.account_id == account_id
        )
    )
    return int(result.scalar_one())
