"""Read-only queries over the append-only ledger, for the admin/audit surface.

Seeded by the idempotency inspection endpoint (see DECISIONS.md →
idempotency-sweep-min-age); this is the first broader slice — a per-account
journal — that the admin feature hub (roadmap item 12) grows from. Nothing here
mutates state: it is a straight read over `postings`/`transactions`, scoped by
tenant so one tenant's support ticket can never surface another tenant's rows.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data.tables.accounts import Account
from data.tables.transactions import Posting, Transaction

DEFAULT_PAGE_SIZE = 50


@dataclass(frozen=True)
class JournalRow:
    """One posting joined with its parent transaction's audit fields."""

    posting_id: uuid.UUID
    transaction_id: uuid.UUID
    amount: int
    effective_at: datetime
    created_at: datetime
    memo: str
    corrects_id: uuid.UUID | None


async def account_journal(
    session: AsyncSession,
    tenant_id: str,
    account_id: uuid.UUID,
    after: datetime | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
) -> list[JournalRow] | None:
    """Return up to `limit` postings for an account, oldest first.

    Returns ``None`` if the account doesn't exist (or belongs to another
    tenant), so the router can 404 without leaking cross-tenant existence.
    `after` is an exclusive cursor on `effective_at` for pagination.
    """
    account = await session.get(Account, account_id)
    if account is None or account.tenant_id != tenant_id:
        return None

    stmt = (
        select(Posting, Transaction)
        .join(Transaction, Posting.transaction_id == Transaction.id)
        .where(Posting.account_id == account_id)
        .order_by(Posting.effective_at, Posting.id)
        .limit(limit)
    )
    if after is not None:
        stmt = stmt.where(Posting.effective_at > after)

    rows = await session.execute(stmt)
    return [
        JournalRow(
            posting_id=posting.id,
            transaction_id=transaction.id,
            amount=posting.amount,
            effective_at=posting.effective_at,
            created_at=posting.created_at,
            memo=transaction.memo,
            corrects_id=transaction.corrects_id,
        )
        for posting, transaction in rows.all()
    ]
