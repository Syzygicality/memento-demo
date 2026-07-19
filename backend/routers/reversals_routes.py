"""Reversal endpoints — compensating entries for a posted transaction."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import SessionDep, TenantDep
from services.idempotency_store import IdempotencyConflict
from schemas.reversals_schemas import ReversalResponse, ReverseTransactionRequest
from services.reversals_service import (
    AlreadyReversedError,
    CannotReverseReversalError,
    TransactionNotFoundError,
    reverse_transaction,
)

router = APIRouter()


@router.post("/{transaction_id}/reverse", response_model=ReversalResponse)
async def reverse_transaction_endpoint(
    transaction_id: uuid.UUID,
    req: ReverseTransactionRequest,
    tenant_id: str = TenantDep,
    session: AsyncSession = SessionDep,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> ReversalResponse:
    """Post a compensating transaction that negates every leg of ``transaction_id``.

    Requires an ``Idempotency-Key``: a retried request with the same key
    returns the original reversal and never posts twice.
    """
    try:
        _, response = await reverse_transaction(
            session, tenant_id, transaction_id, req, idempotency_key
        )
        return response
    except IdempotencyConflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except TransactionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except (AlreadyReversedError, CannotReverseReversalError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
