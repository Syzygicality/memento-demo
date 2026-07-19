"""Postgres-backed idempotency store.

The store records a client key with a fingerprint of the request body and the
response to replay. Its defining property is that it participates in the caller's
transaction: ``reserve`` inserts the record with the *same* session the posting
uses, so the key and the money either both commit or both roll back. A Redis
store could not offer that atomicity, which is why this moved to Postgres (see
DECISIONS.md → idempotency-postgres).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data.tables.idempotency import IdempotencyRecord


class IdempotencyConflict(Exception):
    """Same key, different request body — a client bug, surfaced as 409."""


@dataclass(frozen=True)
class Replay:
    """A stored result to return instead of re-executing."""

    status_code: int
    body: dict[str, Any]


def fingerprint(body: dict[str, Any]) -> str:
    """SHA-256 over the canonicalized request body."""
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


async def lookup(
    session: AsyncSession, tenant_id: str, endpoint: str, key: str, body: dict[str, Any]
) -> Replay | None:
    """Return a replay if this key was already completed; raise on a body mismatch."""
    existing = await session.get(IdempotencyRecord, (tenant_id, endpoint, key))
    if existing is None:
        return None
    if existing.request_fingerprint != fingerprint(body):
        raise IdempotencyConflict(f"key {key!r} reused with a different body")
    return Replay(existing.status_code, json.loads(existing.response_json))


async def record(
    session: AsyncSession,
    tenant_id: str,
    endpoint: str,
    key: str,
    body: dict[str, Any],
    response: dict[str, Any],
    status_code: int = 200,
) -> None:
    """Persist the result in the caller's transaction (no commit here)."""
    session.add(
        IdempotencyRecord(
            tenant_id=tenant_id,
            endpoint=endpoint,
            key=key,
            request_fingerprint=fingerprint(body),
            response_json=json.dumps(response),
            status_code=status_code,
        )
    )


async def keys_for_tenant(session: AsyncSession, tenant_id: str) -> list[str]:
    """Return recorded keys for a tenant (debug/admin surface)."""
    rows = await session.execute(
        select(IdempotencyRecord.key).where(IdempotencyRecord.tenant_id == tenant_id)
    )
    return [r[0] for r in rows.all()]
