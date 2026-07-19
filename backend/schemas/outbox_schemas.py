"""Outbox event request/response shapes."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from data.tables.outbox import OutboxEvent, OutboxStatus


class OutboxEventResponse(BaseModel):
    """A durable event, its delivery status, and its decoded payload."""

    id: uuid.UUID
    transaction_id: uuid.UUID
    event_type: str
    payload: dict[str, Any]
    status: OutboxStatus
    created_at: datetime
    published_at: datetime | None = None

    @classmethod
    def from_row(cls, event: OutboxEvent) -> OutboxEventResponse:
        """Build a response from the stored row, decoding its JSON payload."""
        return cls(
            id=event.id,
            transaction_id=event.transaction_id,
            event_type=event.event_type,
            payload=json.loads(event.payload),
            status=event.status,
            created_at=event.created_at,
            published_at=event.published_at,
        )


class DispatchResponse(BaseModel):
    """The events a dispatch call moved from ``pending`` to ``published``."""

    dispatched: list[OutboxEventResponse]
