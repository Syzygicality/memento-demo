"""Statement generation.

A statement is a point-in-time view of an account's postings, ordered by
``effective_at``, between two instants. Statements are immutable once issued: the
generator only reads postings (which are themselves append-only), so re-issuing a
statement for a closed period yields byte-identical output. Rows are streamed
from a server-side cursor rather than buffered, because a month-end statement for
a busy account exceeds a comfortable memory budget (see DECISIONS.md →
statement-streamed-export).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data.tables.transactions import Posting


@dataclass(frozen=True)
class StatementRow:
    """One line in a rendered statement, with a running balance."""

    posting_id: uuid.UUID
    effective_at: datetime
    amount: int
    running_balance: int


async def stream_statement(
    session: AsyncSession,
    account_id: uuid.UUID,
    start: datetime,
    end: datetime,
    opening_balance: int = 0,
) -> AsyncIterator[StatementRow]:
    """Yield statement rows in effective-time order, carrying a running balance."""
    stmt = (
        select(Posting)
        .where(Posting.account_id == account_id)
        .where(Posting.effective_at >= start)
        .where(Posting.effective_at < end)
        .order_by(Posting.effective_at, Posting.created_at)
        .execution_options(yield_per=500)
    )
    running = opening_balance
    result = await session.stream(stmt)
    async for row in result.scalars():
        running += row.amount
        yield StatementRow(row.id, row.effective_at, row.amount, running)
