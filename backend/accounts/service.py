"""Account lifecycle.

Opening an account also inserts its zero balance snapshot in the same
transaction, so the invariant "every open account has a balance row" holds from
creation and the posting engine never has to create one on a hot path. Currency
is captured at open time and is immutable thereafter.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from accounts.schemas import AccountResponse, OpenAccountRequest
from data.tables.accounts import Account
from data.tables.balances import AccountBalance


async def open_account(
    session: AsyncSession, tenant_id: str, req: OpenAccountRequest
) -> AccountResponse:
    """Create an account and its zero balance snapshot atomically."""
    account = Account(
        tenant_id=tenant_id,
        path=req.path,
        name=req.name,
        normal_balance=req.normal_balance,
        currency=req.currency,
    )
    session.add(account)
    await session.flush()
    session.add(AccountBalance(account_id=account.id, tenant_id=tenant_id, balance=0))
    await session.commit()
    return AccountResponse(
        id=account.id,
        path=account.path,
        name=account.name,
        normal_balance=account.normal_balance,
        currency=account.currency,
        balance=0,
        is_open=account.is_open,
    )


async def get_account(
    session: AsyncSession, tenant_id: str, account_id: uuid.UUID
) -> AccountResponse | None:
    """Fetch an account with its current balance, or None if not this tenant's."""
    account = await session.get(Account, account_id)
    if account is None or account.tenant_id != tenant_id:
        return None
    balance = await session.get(AccountBalance, account_id)
    return AccountResponse(
        id=account.id,
        path=account.path,
        name=account.name,
        normal_balance=account.normal_balance,
        currency=account.currency,
        balance=balance.balance if balance else 0,
        is_open=account.is_open,
    )
