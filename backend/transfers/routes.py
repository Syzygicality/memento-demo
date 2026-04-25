"""Transfer endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import SessionDep, TenantDep
from idempotency.store import IdempotencyConflict
from transfers.schemas import TransferRequest, TransferResponse
from transfers.service import (
    CurrencyMismatchError,
    InsufficientFundsError,
    execute_transfer,
)

router = APIRouter()


@router.post("", response_model=TransferResponse)
async def create_transfer(
    req: TransferRequest,
    tenant_id: str = TenantDep,
    session: AsyncSession = SessionDep,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> TransferResponse:
    """Move money idempotently.

    The ``Idempotency-Key`` header is required: a retried request with the same
    key returns the original result and never posts twice.
    """
    try:
        _, response = await execute_transfer(session, tenant_id, req, idempotency_key)
        return response
    except IdempotencyConflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except (InsufficientFundsError, CurrencyMismatchError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
