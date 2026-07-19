"""Account endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from schemas.accounts_schemas import AccountResponse, OpenAccountRequest
from services.accounts_service import get_account, open_account
from api.deps import SessionDep, TenantDep

router = APIRouter()


@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def open_account_endpoint(
    req: OpenAccountRequest,
    tenant_id: str = TenantDep,
    session: AsyncSession = SessionDep,
) -> AccountResponse:
    """Open a new account (and its zero balance snapshot)."""
    return await open_account(session, tenant_id, req)


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account_endpoint(
    account_id: uuid.UUID,
    tenant_id: str = TenantDep,
    session: AsyncSession = SessionDep,
) -> AccountResponse:
    """Fetch one account with its materialized balance."""
    account = await get_account(session, tenant_id, account_id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    return account
