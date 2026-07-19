"""Hold (authorization) endpoints — place, capture, release."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import SessionDep, TenantDep
from holds.schemas import CaptureHoldRequest, HoldResponse, PlaceHoldRequest
from holds.service import (
    HoldNotFoundError,
    HoldStateError,
    capture_hold,
    place_hold,
    release_hold,
)
from idempotency.store import IdempotencyConflict
from transfers.service import CurrencyMismatchError, InsufficientFundsError

router = APIRouter()


@router.post("", response_model=HoldResponse)
async def place_hold_endpoint(
    req: PlaceHoldRequest,
    tenant_id: str = TenantDep,
    session: AsyncSession = SessionDep,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> HoldResponse:
    """Reserve funds on an account.

    Requires an ``Idempotency-Key``: a retried request with the same key returns
    the original hold and never reserves twice.
    """
    try:
        _, response = await place_hold(session, tenant_id, req, idempotency_key)
        return response
    except IdempotencyConflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except InsufficientFundsError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.post("/{hold_id}/capture", response_model=HoldResponse)
async def capture_hold_endpoint(
    hold_id: uuid.UUID,
    req: CaptureHoldRequest,
    tenant_id: str = TenantDep,
    session: AsyncSession = SessionDep,
) -> HoldResponse:
    """Capture a hold into a transfer to a destination account.

    Idempotent by the hold: capturing an already-captured hold replays the
    original result rather than posting again.
    """
    try:
        return await capture_hold(session, tenant_id, hold_id, req)
    except HoldNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except (HoldStateError, InsufficientFundsError, CurrencyMismatchError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.post("/{hold_id}/release", response_model=HoldResponse)
async def release_hold_endpoint(
    hold_id: uuid.UUID,
    tenant_id: str = TenantDep,
    session: AsyncSession = SessionDep,
) -> HoldResponse:
    """Void an active hold, freeing its reservation. Idempotent by hold state."""
    try:
        return await release_hold(session, tenant_id, hold_id)
    except HoldNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except HoldStateError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
