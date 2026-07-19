"""Transfer orchestration.

A transfer is the high-level, idempotent money-movement API over the posting
engine. One transfer maps to exactly one balanced transaction (a debit leg and a
credit leg) committed atomically with its idempotency record. The flow:

1. Look up the idempotency key; replay the stored result if present.
2. Take a per-account advisory lock on the source so concurrent transfers can't
   both pass the funds check.
3. Verify sufficient *available* funds against the (locked) source — posted
   balance minus anything reserved by active holds, so a transfer can never
   spend funds a hold has already reserved (see DECISIONS.md →
   available-vs-posted-split, which superseded the raw-posted funds check).
4. Post the balanced transaction, folding both snapshots. A cross-currency
   transfer is *not* rejected: it routes through per-currency conversion
   accounts at a resolved, provenance-tagged rate, so each leg stays
   single-currency and still balances to zero (see DECISIONS.md →
   fx-conversion-accounts, which supersedes currency-fixed-per-account).
5. Record the idempotency result — in the same transaction — and commit.

Everything from step 2 onward runs in a single DB transaction, so a crash leaves
neither a posting nor an idempotency record behind.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from data.tables.accounts import Account
from data.tables.balances import AccountBalance
from money.types import Minor, negate
from services import idempotency_store as store
from services.balances_service import available_balance
from services.fx_service import route_conversion
from services.postings_engine import PostingSpec, post_transaction
from services.transfers_locking import account_lock
from schemas.transfers_schemas import TransferRequest, TransferResponse

ENDPOINT = "transfers.create"


class InsufficientFundsError(Exception):
    """The source account cannot cover the transfer."""


class CurrencyMismatchError(Exception):
    """A cross-currency movement could not be routed (no conversion path).

    Cross-currency transfers are no longer rejected outright — they route
    through conversion accounts (see DECISIONS.md → fx-conversion-accounts). This
    is now raised only when that routing is impossible: no effective rate, or no
    provisioned conversion account for one side.
    """


async def execute_transfer(
    session: AsyncSession,
    tenant_id: str,
    req: TransferRequest,
    idempotency_key: str,
) -> tuple[int, TransferResponse]:
    """Run a transfer idempotently. Returns ``(status_code, response)``."""
    body = req.model_dump(mode="json")
    replay = await store.lookup(session, tenant_id, ENDPOINT, idempotency_key, body)
    if replay is not None:
        return replay.status_code, TransferResponse.model_validate(replay.body)

    src = await _require_account(session, tenant_id, req.source_account_id)
    dst = await _require_account(session, tenant_id, req.destination_account_id)

    async with account_lock(session, req.source_account_id):
        src_balance = await available_balance(session, tenant_id, req.source_account_id)
        if src_balance is None:
            raise InsufficientFundsError(f"no balance snapshot for {req.source_account_id}")
        if src_balance.available < req.amount:
            raise InsufficientFundsError(
                f"available {src_balance.available} < requested {req.amount}"
            )

        effective_at = req.effective_at or datetime.now()
        amount = Minor(req.amount)

        if src.currency != dst.currency:
            # Cross-currency: route the value through per-currency conversion
            # accounts. Each leg is single-currency and balances on its own; the
            # source's balancing debit leg is what leaves this account. The
            # idempotency record still commits in this same transaction.
            conversion = await route_conversion(
                session, tenant_id, src, dst, amount, effective_at, req.memo
            )
            txn_id = conversion.debit_transaction_id
        else:
            txn = await post_transaction(
                session,
                tenant_id,
                specs=[
                    PostingSpec(req.source_account_id, negate(amount), effective_at),
                    PostingSpec(req.destination_account_id, amount, effective_at),
                ],
                memo=req.memo,
            )
            txn_id = txn.id

        src_after = await _balance(session, tenant_id, req.source_account_id)
        dst_after = await _balance(session, tenant_id, req.destination_account_id)
        response = TransferResponse(
            transaction_id=txn_id,
            source_balance=src_after.balance,
            destination_balance=dst_after.balance,
        )
        await store.record(
            session, tenant_id, ENDPOINT, idempotency_key, body, response.model_dump(mode="json")
        )
        await session.commit()
    return 200, response


async def _require_account(
    session: AsyncSession, tenant_id: str, account_id: object
) -> Account:
    account = await session.get(Account, account_id)
    if account is None or account.tenant_id != tenant_id or not account.is_open:
        raise InsufficientFundsError(f"account {account_id} not found or closed")
    return account


async def _balance(
    session: AsyncSession, tenant_id: str, account_id: object
) -> AccountBalance:
    balance = await session.get(AccountBalance, account_id)
    if balance is None or balance.tenant_id != tenant_id:
        raise InsufficientFundsError(f"no balance snapshot for {account_id}")
    return balance
