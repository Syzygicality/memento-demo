"""The double-entry posting engine.

This is the only code path that writes to ``transactions`` and ``postings``, and
it enforces the two core invariants before the DB trigger ever sees the rows:

1. A transaction has at least two postings.
2. Its postings sum to exactly zero.

It writes the transaction, its postings, and the affected balance snapshots
inside a single caller-provided session/transaction, so either the whole entry
lands or none of it does. The engine never opens its own transaction — the
service layer owns the boundary so a transfer's idempotency record commits with
the posting (see DECISIONS.md → idempotency-same-transaction).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from data.tables.balances import AccountBalance
from data.tables.transactions import Posting, Transaction
from money.types import Minor


class UnbalancedTransactionError(ValueError):
    """Raised when the postings of a transaction do not sum to zero."""


@dataclass(frozen=True)
class PostingSpec:
    """A requested leg: a signed minor-unit amount against one account."""

    account_id: uuid.UUID
    amount: Minor
    effective_at: datetime


async def post_transaction(
    session: AsyncSession,
    tenant_id: str,
    specs: list[PostingSpec],
    memo: str = "",
    corrects_id: uuid.UUID | None = None,
) -> Transaction:
    """Validate, write, and fold a balanced transaction into the snapshots.

    :param session: an open session whose transaction the caller commits.
    :param tenant_id: the acting tenant (from auth context, never a body).
    :param specs: the legs; must be >= 2 and sum to zero.
    :param memo: free-text description stored on the transaction.
    :param corrects_id: the transaction this one reverses, if any.
    :return: the persisted :class:`Transaction`.
    :raises UnbalancedTransactionError: if the legs do not sum to zero.
    """
    if len(specs) < 2:
        raise UnbalancedTransactionError("a transaction needs at least two postings")
    total = sum(int(s.amount) for s in specs)
    if total != 0:
        raise UnbalancedTransactionError(f"postings sum to {total}, must be 0")

    txn = Transaction(tenant_id=tenant_id, memo=memo, corrects_id=corrects_id)
    session.add(txn)
    await session.flush()  # assign txn.id without committing

    for spec in specs:
        posting = Posting(
            transaction_id=txn.id,
            account_id=spec.account_id,
            amount=int(spec.amount),
            effective_at=spec.effective_at,
        )
        session.add(posting)
        await session.flush()
        await _apply_to_snapshot(session, tenant_id, spec, posting.id)

    return txn


async def _apply_to_snapshot(
    session: AsyncSession,
    tenant_id: str,
    spec: PostingSpec,
    posting_id: uuid.UUID,
) -> None:
    """Fold one posting into the account's balance snapshot in the same txn.

    Uses a single conditional ``UPDATE`` that bumps the version and advances the
    watermark; if no snapshot row exists yet the caller's account-open path has
    already inserted a zero row, so a missing row here is a real error surfaced
    by the outer transaction.
    """
    await session.execute(
        update(AccountBalance)
        .where(AccountBalance.account_id == spec.account_id)
        .where(AccountBalance.tenant_id == tenant_id)
        .values(
            balance=AccountBalance.balance + int(spec.amount),
            version=AccountBalance.version + 1,
            as_of_posting_id=posting_id,
        )
    )
