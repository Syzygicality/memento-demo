"""Reversal orchestration — compensating entries, never mutation.

A reversal is a new, balanced transaction whose legs are the exact negation of
an earlier transaction's, linked back via ``corrects_id`` (see DECISIONS.md →
append-only-ledger). Two guardrails keep a reversal from itself unbalancing the
ledger:

* **at most one reversal per transaction** — a transaction that already has a
  reversal cannot be reversed again, so retries and double-clicks land on the
  same compensating entry rather than compensating twice.
* **a reversal cannot itself be reversed** — reversing a reversal would just
  restore the original entry, which is what a fresh, ordinary transaction is
  for; chaining `corrects_id` back through a reversal adds no information and
  is rejected instead.

Idempotent by ``Idempotency-Key``, like a transfer, since it mints a new
transaction (see DECISIONS.md → idempotency-postgres).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data.tables.transactions import Posting, Transaction
from services import idempotency_store as store
from money.types import Minor, negate
from services.postings_engine import PostingSpec, post_transaction
from schemas.reversals_schemas import ReversalResponse, ReverseTransactionRequest

REVERSE_ENDPOINT = "reversals.create"


class TransactionNotFoundError(Exception):
    """No such transaction for this tenant."""


class AlreadyReversedError(Exception):
    """The transaction already has a reversal; reverse the reversal's cause, not it again."""


class CannotReverseReversalError(Exception):
    """The transaction is itself a reversal and may not be reversed."""


async def reverse_transaction(
    session: AsyncSession,
    tenant_id: str,
    transaction_id: uuid.UUID,
    req: ReverseTransactionRequest,
    idempotency_key: str,
) -> tuple[int, ReversalResponse]:
    """Post a compensating transaction that negates every leg of ``transaction_id``."""
    body = req.model_dump(mode="json") | {"transaction_id": str(transaction_id)}
    replay = await store.lookup(session, tenant_id, REVERSE_ENDPOINT, idempotency_key, body)
    if replay is not None:
        return replay.status_code, ReversalResponse.model_validate(replay.body)

    original = await _require_transaction(session, tenant_id, transaction_id)

    if original.corrects_id is not None:
        raise CannotReverseReversalError(
            f"transaction {transaction_id} is itself a reversal and cannot be reversed"
        )

    existing_reversal = await session.execute(
        select(Transaction.id)
        .where(Transaction.tenant_id == tenant_id)
        .where(Transaction.corrects_id == transaction_id)
    )
    if existing_reversal.first() is not None:
        raise AlreadyReversedError(f"transaction {transaction_id} already has a reversal")

    postings = (
        await session.execute(
            select(Posting).where(Posting.transaction_id == transaction_id)
        )
    ).scalars().all()
    if not postings:
        raise TransactionNotFoundError(f"transaction {transaction_id} has no postings")

    effective_at = datetime.now()
    specs = [
        PostingSpec(
            account_id=posting.account_id,
            amount=negate(Minor(posting.amount)),
            effective_at=effective_at,
        )
        for posting in postings
    ]

    reversal = await post_transaction(
        session,
        tenant_id,
        specs=specs,
        memo=req.memo or f"reversal of {transaction_id}",
        corrects_id=transaction_id,
    )

    response = ReversalResponse(
        id=reversal.id,
        corrects_id=transaction_id,
        memo=reversal.memo,
        created_at=reversal.created_at,
    )
    await store.record(
        session,
        tenant_id,
        REVERSE_ENDPOINT,
        idempotency_key,
        body,
        response.model_dump(mode="json"),
    )
    await session.commit()
    return 200, response


async def _require_transaction(
    session: AsyncSession, tenant_id: str, transaction_id: uuid.UUID
) -> Transaction:
    txn = await session.get(Transaction, transaction_id)
    if txn is None or txn.tenant_id != tenant_id:
        raise TransactionNotFoundError(f"transaction {transaction_id} not found")
    return txn
