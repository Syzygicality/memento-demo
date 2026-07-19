"""Balance endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import SessionDep, TenantDep
from balances.service import available_balance

router = APIRouter()


@router.get("/{account_id}")
async def get_balance_endpoint(
    account_id: uuid.UUID,
    tenant_id: str = TenantDep,
    session: AsyncSession = SessionDep,
) -> dict[str, int | str]:
    """Return the posted, held, and available balances for an account.

    ``posted`` is the settled snapshot; ``available`` is what can still be spent
    once active holds are subtracted; ``held`` is the difference.
    """
    balance = await available_balance(session, tenant_id, account_id)
    if balance is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    return {
        "account_id": str(account_id),
        "posted": balance.posted,
        "held": balance.held,
        "available": balance.available,
        # Retained for callers that predate the available/posted split.
        "balance": balance.posted,
    }
