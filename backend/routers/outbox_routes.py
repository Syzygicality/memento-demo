"""Outbox endpoints — inspect and dispatch durable transaction events."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import SessionDep, TenantDep
from data.tables.outbox import OutboxStatus
from schemas.outbox_schemas import DispatchResponse, OutboxEventResponse
from services.outbox_service import dispatch_pending, list_events

router = APIRouter()


@router.get("", response_model=list[OutboxEventResponse])
async def list_events_endpoint(
    status: OutboxStatus | None = None,
    limit: int = 100,
    tenant_id: str = TenantDep,
    session: AsyncSession = SessionDep,
) -> list[OutboxEventResponse]:
    """List this tenant's outbox events, oldest first."""
    events = await list_events(session, tenant_id, status=status, limit=limit)
    return [OutboxEventResponse.from_row(e) for e in events]


@router.post("/dispatch", response_model=DispatchResponse)
async def dispatch_endpoint(
    limit: int = 100,
    tenant_id: str = TenantDep,
    session: AsyncSession = SessionDep,
) -> DispatchResponse:
    """Publish up to ``limit`` pending events, oldest first.

    Stands in for a background relay; safe to call repeatedly since publishing
    is at-least-once and idempotent by event id on the consumer side.
    """
    dispatched = await dispatch_pending(session, tenant_id, limit=limit)
    response_events = [OutboxEventResponse.from_row(e) for e in dispatched]
    return DispatchResponse(dispatched=response_events)
