"""Integration tests: the transactional outbox against a real per-test Postgres.

Asserts that every posted transaction gets exactly one outbox event in the same
transaction, that a retried idempotent transfer does not enqueue a second event,
and that dispatch marks pending events published exactly once (DECISIONS.md →
outbox-same-transaction, outbox-at-least-once).
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

pytest.importorskip("pytest_postgresql")

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

from data.tables.accounts import Account, NormalBalance  # noqa: E402
from data.tables.balances import AccountBalance  # noqa: E402
from data.tables.outbox import OutboxEvent, OutboxStatus  # noqa: E402
from money.types import Currency  # noqa: E402
from outbox.service import dispatch_pending, list_events  # noqa: E402
from transfers.schemas import TransferRequest  # noqa: E402
from transfers.service import execute_transfer  # noqa: E402


@pytest.fixture
def migrated_dsn(postgresql) -> str:  # type: ignore[no-untyped-def]
    """Apply migrations to a fresh per-test Postgres and return its async DSN."""
    dsn = (
        f"postgresql+asyncpg://{postgresql.info.user}:@"
        f"{postgresql.info.host}:{postgresql.info.port}/{postgresql.info.dbname}"
    )
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", dsn)
    command.upgrade(cfg, "head")
    return dsn


@pytest.fixture
async def session(migrated_dsn: str) -> AsyncSession:  # type: ignore[misc]
    """A session against the migrated per-test Postgres."""
    engine = create_async_engine(migrated_dsn)
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


async def test_transfer_enqueues_one_outbox_event(session: AsyncSession) -> None:
    src = await _open_account(session, balance=10_000)
    dst = await _open_account(session, balance=0)

    _, result = await execute_transfer(
        session,
        "acme",
        TransferRequest(source_account_id=src, destination_account_id=dst, amount=2_000),
        "t-1",
    )

    count = await session.scalar(
        select(func.count()).select_from(OutboxEvent).where(
            OutboxEvent.transaction_id == result.transaction_id
        )
    )
    assert count == 1

    events = await list_events(session, "acme")
    assert len(events) == 1
    event = events[0]
    assert event.status == OutboxStatus.PENDING
    payload = json.loads(event.payload)
    assert payload["transaction_id"] == str(result.transaction_id)
    assert {p["account_id"] for p in payload["postings"]} == {str(src), str(dst)}


async def test_retried_transfer_does_not_duplicate_event(session: AsyncSession) -> None:
    src = await _open_account(session, balance=10_000)
    dst = await _open_account(session, balance=0)
    req = TransferRequest(source_account_id=src, destination_account_id=dst, amount=1_000)

    await execute_transfer(session, "acme", req, "t-1")
    await execute_transfer(session, "acme", req, "t-1")  # idempotent replay

    events = await list_events(session, "acme")
    assert len(events) == 1


async def test_dispatch_publishes_pending_events_once(session: AsyncSession) -> None:
    src = await _open_account(session, balance=10_000)
    dst = await _open_account(session, balance=0)
    await execute_transfer(
        session,
        "acme",
        TransferRequest(source_account_id=src, destination_account_id=dst, amount=500),
        "t-1",
    )

    dispatched = await dispatch_pending(session, "acme")
    assert len(dispatched) == 1
    assert dispatched[0].status == OutboxStatus.PUBLISHED
    assert dispatched[0].published_at is not None

    # A second dispatch has nothing left to publish.
    again = await dispatch_pending(session, "acme")
    assert again == []
