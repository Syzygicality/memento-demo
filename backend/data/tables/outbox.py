"""Outbox event table — durable, transaction-scoped event records.

Every committed transaction gets exactly one ``OutboxEvent`` row written in the
*same* database transaction as its postings (see DECISIONS.md →
outbox-same-transaction). Nothing in this codebase ever ``UPDATE``s a row's
``payload``; a dispatch only flips ``status`` from ``PENDING`` to
``PUBLISHED`` and stamps ``published_at``, so the event record itself stays as
immutable as the transaction it describes.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlmodel import Field, SQLModel


class OutboxStatus(StrEnum):
    """Delivery state of an outbox event."""

    # Written, not yet handed to a downstream consumer.
    PENDING = "pending"
    # Delivered at least once. Consumers must be idempotent (see DECISIONS.md →
    # outbox-at-least-once).
    PUBLISHED = "published"


class OutboxEvent(SQLModel, table=True):
    """One durable event describing a committed transaction."""

    __tablename__ = "outbox_events"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    tenant_id: str = Field(index=True)
    transaction_id: uuid.UUID = Field(foreign_key="transactions.id", index=True)
    event_type: str = Field(default="transaction.posted")
    # JSON-serializable payload; kept as a string column, not JSONB, since it is
    # only ever written once and read back verbatim for delivery.
    payload: str
    status: OutboxStatus = Field(default=OutboxStatus.PENDING, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now())
    published_at: datetime | None = Field(default=None)
