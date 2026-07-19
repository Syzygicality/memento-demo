"""Idempotency key inspection response shapes."""

from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import BaseModel

from data.tables.idempotency import IdempotencyRecord


class IdempotencyKeyResponse(BaseModel):
    """Status of a single stored idempotency key, for support/admin lookups."""

    endpoint: str
    key: str
    status_code: int
    created_at: datetime
    swept_at: datetime

    @classmethod
    def from_row(
        cls, record: IdempotencyRecord, min_age: timedelta
    ) -> IdempotencyKeyResponse:
        """Build a response, projecting when the sweeper will reclaim this record."""
        return cls(
            endpoint=record.endpoint,
            key=record.key,
            status_code=record.status_code,
            created_at=record.created_at,
            swept_at=record.created_at + min_age,
        )
