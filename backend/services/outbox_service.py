"""Outbox read + dispatch — the consumer side of the transactional outbox.

Writing an event is the posting engine's job (``postings/engine.py``); this
module only reads events back and marks them delivered. ``dispatch_pending``
stands in for a real relay (a CDC tailer or a polling publisher would call this
same function) — it is deliberately at-least-once: an event is only flipped to
``PUBLISHED`` after the caller's delivery attempt returns, and a crash between
"delivered" and "marked published" replays the event on the next dispatch (see
DECISIONS.md → outbox-at-least-once). Consumers must therefore de-duplicate by
``id``.

Events are read and dispatched in ``(created_at, id)`` order per tenant, which
is the ordering guarantee downstream consumers get (see DECISIONS.md →
outbox-order-by-sequence).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data.tables.outbox import OutboxEvent, OutboxStatus


async def list_events(
    session: AsyncSession,
    tenant_id: str,
    status: OutboxStatus | None = None,
    limit: int = 100,
) -> list[OutboxEvent]:
    """Return this tenant's events, oldest first, optionally filtered by status."""
    stmt = (
        select(OutboxEvent)
        .where(OutboxEvent.tenant_id == tenant_id)
        .order_by(OutboxEvent.created_at, OutboxEvent.id)
        .limit(limit)
    )
    if status is not None:
        stmt = stmt.where(OutboxEvent.status == status)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def dispatch_pending(
    session: AsyncSession, tenant_id: str, limit: int = 100
) -> list[OutboxEvent]:
    """Mark up to ``limit`` pending events as published, oldest first.

    Stands in for handing each event to a webhook/downstream-ledger sink; a real
    relay would attempt delivery per event here and only mark the ones that
    succeeded, leaving the rest ``PENDING`` for the next pass.
    """
    pending = await list_events(
        session, tenant_id, status=OutboxStatus.PENDING, limit=limit
    )
    now = datetime.now()
    for event in pending:
        event.status = OutboxStatus.PUBLISHED
        event.published_at = now
        session.add(event)
    if pending:
        await session.commit()
    return pending
