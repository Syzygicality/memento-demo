"""Idempotency inspection endpoint — read-only, for support and debugging.

Lets support look up whether a client's idempotency key was recorded, what it
will replay, and when the sweeper (`services/idempotency_sweeper.py`) will
reclaim it, without granting write access to the store itself.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import SessionDep, TenantDep
from schemas.idempotency_schemas import IdempotencyKeyResponse
from services.idempotency_store import get_record
from services.idempotency_sweeper import DEFAULT_MIN_AGE

router = APIRouter()


@router.get("/{endpoint}/{key}", response_model=IdempotencyKeyResponse)
async def get_idempotency_key_endpoint(
    endpoint: str,
    key: str,
    tenant_id: str = TenantDep,
    session: AsyncSession = SessionDep,
) -> IdempotencyKeyResponse:
    """Return the stored status for one tenant-scoped idempotency key."""
    record = await get_record(session, tenant_id, endpoint, key)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No idempotency record for this key (never seen, or already swept)",
        )
    return IdempotencyKeyResponse.from_row(record, min_age=DEFAULT_MIN_AGE)
