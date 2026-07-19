"""Unit tests for the idempotency key inspection lookup.

Exercises `services.idempotency_store.get_record` directly against the schemas
used by the read-only `/idempotency/{endpoint}/{key}` endpoint, without needing a
live Postgres.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from schemas.idempotency_schemas import IdempotencyKeyResponse
from services.idempotency_store import get_record


class _FakeSession:
    def __init__(self, record: object | None) -> None:
        self._record = record

    async def get(self, _model: object, _pk: tuple[str, str, str]) -> object | None:
        return self._record


class _Record:
    def __init__(self) -> None:
        from datetime import datetime

        self.tenant_id = "acme"
        self.endpoint = "transfers"
        self.key = "k-1"
        self.status_code = 200
        self.created_at = datetime(2026, 6, 1, 12, 0, 0)


async def test_get_record_returns_none_when_absent() -> None:
    session = _FakeSession(None)
    result = await get_record(session, "acme", "transfers", "missing-key")  # type: ignore[arg-type]
    assert result is None


async def test_response_projects_swept_at_from_min_age() -> None:
    record = _Record()
    response = IdempotencyKeyResponse.from_row(record, min_age=timedelta(hours=24))  # type: ignore[arg-type]
    assert response.swept_at == record.created_at + timedelta(hours=24)
    assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__])
