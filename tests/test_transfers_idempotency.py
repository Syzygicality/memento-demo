"""Integration test: a retried transfer posts exactly once.

Requires Postgres (pytest-postgresql + `initdb` on PATH). It builds a fresh
database, applies migrations, and drives a real transfer twice with the same
Idempotency-Key, asserting the second call replays the first result and no second
transaction is written. This is the test that proves the idempotency record and
the posting commit atomically (DECISIONS.md → idempotency-same-transaction).
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

pytest.importorskip("pytest_postgresql")

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

from data.tables.accounts import Account, NormalBalance  # noqa: E402
from data.tables.balances import AccountBalance  # noqa: E402
from data.tables.transactions import Transaction  # noqa: E402
from money.types import Currency  # noqa: E402
from schemas.transfers_schemas import TransferRequest  # noqa: E402
from services.transfers_service import execute_transfer  # noqa: E402


@pytest.fixture
async def session(postgresql) -> AsyncSession:  # type: ignore[no-untyped-def]
    """A session against a migrated per-test Postgres."""
    dsn = (
        f"postgresql+asyncpg://{postgresql.info.user}:@"
        f"{postgresql.info.host}:{postgresql.info.port}/{postgresql.info.dbname}"
    )
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", dsn)
    command.upgrade(cfg, "head")

    engine = create_async_engine(dsn)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _open_account(s: AsyncSession, balance: int) -> uuid.UUID:
    acct = Account(
        tenant_id="acme",
        path="assets.cash",
        name="cash",
        normal_balance=NormalBalance.DEBIT,
        currency=Currency.USD,
    )
    s.add(acct)
    await s.flush()
    s.add(AccountBalance(account_id=acct.id, tenant_id="acme", balance=balance))
    await s.commit()
    return acct.id


async def test_retry_with_same_key_posts_once(session: AsyncSession) -> None:
    src = await _open_account(session, balance=10_000)
    dst = await _open_account(session, balance=0)
    req = TransferRequest(
        source_account_id=src,
        destination_account_id=dst,
        amount=2_500,
        effective_at=datetime(2026, 6, 1),
    )

    _, first = await execute_transfer(session, "acme", req, idempotency_key="k-1")
    _, second = await execute_transfer(session, "acme", req, idempotency_key="k-1")

    assert first.transaction_id == second.transaction_id
    count = await session.scalar(select(func.count()).select_from(Transaction))
    assert count == 1
    assert first.source_balance == 7_500
