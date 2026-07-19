"""Unit tests for the admin per-account journal read.

Exercises `services.admin_service.account_journal` directly with a fake
session, without needing a live Postgres.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from services.admin_service import account_journal


class _Account:
    def __init__(self, tenant_id: str) -> None:
        self.tenant_id = tenant_id


class _Posting:
    def __init__(self, account_id: uuid.UUID, effective_at: datetime, amount: int) -> None:
        self.id = uuid.uuid4()
        self.transaction_id = uuid.uuid4()
        self.account_id = account_id
        self.amount = amount
        self.effective_at = effective_at
        self.created_at = effective_at


class _Transaction:
    def __init__(self, id_: uuid.UUID) -> None:
        self.id = id_
        self.memo = "test memo"
        self.corrects_id = None


class _Rows:
    def __init__(self, pairs: list[tuple[_Posting, _Transaction]]) -> None:
        self._pairs = pairs

    def all(self) -> list[tuple[_Posting, _Transaction]]:
        return self._pairs


class _FakeSession:
    def __init__(self, account: object | None, pairs: list[tuple[_Posting, _Transaction]]) -> None:
        self._account = account
        self._pairs = pairs

    async def get(self, _model: object, _pk: uuid.UUID) -> object | None:
        return self._account

    async def execute(self, _stmt: object) -> _Rows:
        return _Rows(self._pairs)


async def test_account_journal_returns_none_for_missing_account() -> None:
    session = _FakeSession(None, [])
    result = await account_journal(session, "acme", uuid.uuid4())  # type: ignore[arg-type]
    assert result is None


async def test_account_journal_returns_none_for_cross_tenant_account() -> None:
    session = _FakeSession(_Account("other-tenant"), [])
    result = await account_journal(session, "acme", uuid.uuid4())  # type: ignore[arg-type]
    assert result is None


async def test_account_journal_returns_rows_for_owned_account() -> None:
    account_id = uuid.uuid4()
    posting = _Posting(account_id, datetime(2026, 6, 1, 12, 0, 0), 500)
    txn = _Transaction(posting.transaction_id)
    session = _FakeSession(_Account("acme"), [(posting, txn)])

    result = await account_journal(session, "acme", account_id)  # type: ignore[arg-type]

    assert result is not None
    assert len(result) == 1
    row = result[0]
    assert row.posting_id == posting.id
    assert row.amount == 500
    assert row.memo == "test memo"
    assert row.corrects_id is None
