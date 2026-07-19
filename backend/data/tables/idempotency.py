"""Idempotency record table.

An idempotency key is scoped per ``(tenant_id, endpoint, key)`` and stores a
fingerprint of the request body plus the serialized response. A replay with the
same fingerprint returns the stored response; a replay of the same key with a
*different* body is a conflict, not a silent second execution (see DECISIONS.md →
idempotency-fingerprint).

The record lives in Postgres — not Redis — specifically so it commits in the same
transaction as the posting it guards (see DECISIONS.md →
idempotency-postgres, which superseded the Redis store).
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel


class IdempotencyRecord(SQLModel, table=True):
    """One stored result for a client-supplied idempotency key."""

    __tablename__ = "idempotency_records"

    tenant_id: str = Field(primary_key=True)
    endpoint: str = Field(primary_key=True)
    key: str = Field(primary_key=True)
    # SHA-256 of the canonicalized request body.
    request_fingerprint: str
    # Serialized response payload replayed on a matching retry.
    response_json: str
    status_code: int = Field(default=200)
    created_at: datetime = Field(default_factory=lambda: datetime.now(), index=True)
