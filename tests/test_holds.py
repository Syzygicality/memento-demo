"""Integration tests: two-phase holds against a real per-test Postgres.

Requires Postgres (pytest-postgresql + `initdb` on PATH). Each test builds a
fresh migrated database and drives the hold service directly, asserting the
available/posted split, that a hold blocks an over-transfer, and that capture and
release resolve the reservation (DECISIONS.md → available-vs-posted-split,
hold-is-reservation-not-posting, hold-capture-idempotent-by-state).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

pytest.importorskip("pytest_postgresql")

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

from services.balances_service import available_balance  # noqa: E402
from data.tables.accounts import Account, NormalBalance  # noqa: E402
from data.tables.balances import AccountBalance  # noqa: E402
from data.tables.holds import Hold, HoldState  # noqa: E402
from data.tables.transactions import Transaction  # noqa: E402
from schemas.holds_schemas import CaptureHoldRequest, PlaceHoldRequest  # noqa: E402
from services.holds_service import capture_hold, place_hold, release_hold  # noqa: E402
from money.types import Currency  # noqa: E402
from schemas.transfers_schemas import TransferRequest  # noqa: E402
from services.transfers_service import InsufficientFundsError, execute_transfer  # noqa: E402


@pytest.fixture
def migrated_dsn(postgresql) -> str:  # type: ignore[no-untyped-def]
    """Apply migrations to a fresh per-test Postgres and return its async DSN.

    Kept synchronous on purpose: Alembic's async ``env.py`` drives migrations
    with ``asyncio.run``, which cannot run inside pytest-asyncio's already-running
    loop, so the upgrade happens here, before any async fixture opens a loop.
    """
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


async def test_place_hold_reduces_available_not_posted(session: AsyncSession) -> None:
    acct = await _open_account(session, balance=10_000)

    _, hold = await place_hold(
        session, "acme", PlaceHoldRequest(account_id=acct, amount=3_000), "h-1"
    )

    assert hold.state == HoldState.ACTIVE
    assert hold.posted_balance == 10_000
    assert hold.available_balance == 7_000
    bal = await available_balance(session, "acme", acct)
    assert bal is not None
    assert bal.posted == 10_000 and bal.available == 7_000


async def test_hold_blocks_transfer_beyond_available(session: AsyncSession) -> None:
    src = await _open_account(session, balance=10_000)
    dst = await _open_account(session, balance=0)
    await place_hold(
        session, "acme", PlaceHoldRequest(account_id=src, amount=8_000), "h-1"
    )

    # 5_000 exceeds available (2_000) even though posted (10_000) would cover it.
    with pytest.raises(InsufficientFundsError):
        await execute_transfer(
            session,
            "acme",
            TransferRequest(source_account_id=src, destination_account_id=dst, amount=5_000),
            "t-1",
        )

    # A transfer within available succeeds.
    _, ok = await execute_transfer(
        session,
        "acme",
        TransferRequest(source_account_id=src, destination_account_id=dst, amount=2_000),
        "t-2",
    )
    assert ok.source_balance == 8_000


async def test_capture_posts_once_and_moves_money(session: AsyncSession) -> None:
    src = await _open_account(session, balance=10_000)
    dst = await _open_account(session, balance=0)
    _, hold = await place_hold(
        session, "acme", PlaceHoldRequest(account_id=src, amount=4_000), "h-1"
    )

    captured = await capture_hold(
        session, "acme", hold.id, CaptureHoldRequest(destination_account_id=dst)
    )

    assert captured.state == HoldState.CAPTURED
    assert captured.captured_amount == 4_000
    # Posted has moved; the reservation is gone, so available == posted again.
    assert captured.posted_balance == 6_000
    assert captured.available_balance == 6_000
    dst_bal = await available_balance(session, "acme", dst)
    assert dst_bal is not None and dst_bal.posted == 4_000

    # Capturing again replays: no second transaction is written.
    again = await capture_hold(
        session, "acme", hold.id, CaptureHoldRequest(destination_account_id=dst)
    )
    assert again.captured_transaction_id == captured.captured_transaction_id
    count = await session.scalar(select(func.count()).select_from(Transaction))
    assert count == 1


async def test_release_frees_the_reservation(session: AsyncSession) -> None:
    acct = await _open_account(session, balance=10_000)
    _, hold = await place_hold(
        session, "acme", PlaceHoldRequest(account_id=acct, amount=3_000), "h-1"
    )
    assert (await available_balance(session, "acme", acct)).available == 7_000  # type: ignore[union-attr]

    released = await release_hold(session, "acme", hold.id)

    assert released.state == HoldState.RELEASED
    assert released.available_balance == 10_000


async def test_place_hold_is_idempotent(session: AsyncSession) -> None:
    acct = await _open_account(session, balance=10_000)
    req = PlaceHoldRequest(account_id=acct, amount=2_500)

    _, first = await place_hold(session, "acme", req, "h-1")
    _, second = await place_hold(session, "acme", req, "h-1")

    assert first.id == second.id
    count = await session.scalar(select(func.count()).select_from(Hold))
    assert count == 1
