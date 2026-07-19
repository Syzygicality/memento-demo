"""Hold orchestration — two-phase money movement.

A hold is the authorization half of a two-phase transfer: reserve funds now,
then capture (move the money) or release (void the reservation) later. The three
operations and their guarantees:

* **place** — idempotent by ``Idempotency-Key`` (like a transfer, since it
  mints a new hold). Under the source account's advisory lock it checks the
  *available* balance — posted minus funds already reserved by other active
  holds — and inserts an ``ACTIVE`` hold. It writes no posting: a hold is a
  reservation, not a money movement (see DECISIONS.md →
  hold-is-reservation-not-posting).
* **capture** — converts the hold into exactly one balanced transaction from the
  held account to a destination, then marks the hold ``CAPTURED``. Capture is
  idempotent by the hold's own id and terminal state: a hold captures at most
  once, so a retry replays the resolved hold rather than posting twice (see
  DECISIONS.md → hold-capture-idempotent-by-state).
* **release** — voids an ``ACTIVE`` hold, freeing its reservation. Also
  idempotent by hold state.

The funds check reads *available*, so a placed hold cannot be spent twice — this
supersedes the raw-posted funds check the transfer path used (see DECISIONS.md →
available-vs-posted-split, which supersedes part of transfer-advisory-lock).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from services.balances_service import available_balance
from config.config import settings
from data.tables.accounts import Account
from data.tables.holds import Hold, HoldState
from schemas.holds_schemas import CaptureHoldRequest, HoldResponse, PlaceHoldRequest
from services import idempotency_store as store
from money.types import Minor, negate
from services.postings_engine import PostingSpec, post_transaction
from services.transfers_locking import account_lock
from services.transfers_service import CurrencyMismatchError, InsufficientFundsError

PLACE_ENDPOINT = "holds.place"


class HoldNotFoundError(Exception):
    """No such hold for this tenant."""


class HoldStateError(Exception):
    """The hold is not in a state that permits the requested operation."""


async def place_hold(
    session: AsyncSession,
    tenant_id: str,
    req: PlaceHoldRequest,
    idempotency_key: str,
) -> tuple[int, HoldResponse]:
    """Reserve funds against an account idempotently. Returns ``(status, response)``."""
    body = req.model_dump(mode="json")
    replay = await store.lookup(session, tenant_id, PLACE_ENDPOINT, idempotency_key, body)
    if replay is not None:
        return replay.status_code, HoldResponse.model_validate(replay.body)

    await _require_account(session, tenant_id, req.account_id)

    async with account_lock(session, req.account_id):
        balance = await available_balance(session, tenant_id, req.account_id)
        if balance is None:
            raise InsufficientFundsError(f"no balance snapshot for {req.account_id}")
        if balance.available < req.amount:
            raise InsufficientFundsError(
                f"available {balance.available} < requested {req.amount}"
            )

        expires_at = req.expires_at or (
            datetime.now() + timedelta(minutes=settings.hold_default_ttl_minutes)
        )
        hold = Hold(
            tenant_id=tenant_id,
            account_id=req.account_id,
            amount=req.amount,
            state=HoldState.ACTIVE,
            memo=req.memo,
            expires_at=expires_at,
        )
        session.add(hold)
        await session.flush()

        after = await available_balance(session, tenant_id, req.account_id)
        assert after is not None  # the snapshot existed a few lines above
        response = _to_response(hold, after.posted, after.available)
        await store.record(
            session,
            tenant_id,
            PLACE_ENDPOINT,
            idempotency_key,
            body,
            response.model_dump(mode="json"),
        )
        await session.commit()
    return 200, response


async def capture_hold(
    session: AsyncSession,
    tenant_id: str,
    hold_id: object,
    req: CaptureHoldRequest,
) -> HoldResponse:
    """Capture a hold into a real transfer to a destination account.

    Idempotent by the hold's terminal state: capturing an already-captured hold
    replays the original result rather than posting a second transaction.
    """
    hold = await _require_hold(session, tenant_id, hold_id)

    if hold.state == HoldState.CAPTURED:
        # Already resolved — replay, do not post again.
        balance = await available_balance(session, tenant_id, hold.account_id)
        posted = balance.posted if balance else 0
        available = balance.available if balance else 0
        return _to_response(hold, posted, available)
    if hold.state != HoldState.ACTIVE:
        raise HoldStateError(f"hold {hold.id} is {hold.state}, cannot capture")

    src = await _require_account(session, tenant_id, hold.account_id)
    dst = await _require_account(session, tenant_id, req.destination_account_id)
    if src.currency != dst.currency:
        raise CurrencyMismatchError("cross-currency capture requires a conversion account")

    capture_amount = req.amount if req.amount is not None else hold.amount
    if capture_amount > hold.amount:
        raise HoldStateError(
            f"capture {capture_amount} exceeds held {hold.amount}"
        )

    async with account_lock(session, hold.account_id):
        # The hold reserved these funds while ACTIVE, so posted must already
        # cover the capture; guard defensively against a drained snapshot.
        before = await available_balance(session, tenant_id, hold.account_id)
        if before is None or before.posted < capture_amount:
            raise InsufficientFundsError(
                f"posted balance cannot cover capture of {capture_amount}"
            )

        effective_at = datetime.now()
        amount = Minor(capture_amount)
        txn = await post_transaction(
            session,
            tenant_id,
            specs=[
                PostingSpec(hold.account_id, negate(amount), effective_at),
                PostingSpec(req.destination_account_id, amount, effective_at),
            ],
            memo=req.memo or hold.memo,
        )

        hold.state = HoldState.CAPTURED
        hold.captured_transaction_id = txn.id
        hold.captured_amount = capture_amount
        hold.resolved_at = effective_at
        session.add(hold)

        after = await available_balance(session, tenant_id, hold.account_id)
        assert after is not None
        response = _to_response(hold, after.posted, after.available)
        await session.commit()
    return response


async def release_hold(
    session: AsyncSession, tenant_id: str, hold_id: object
) -> HoldResponse:
    """Void an active hold, freeing its reservation. Idempotent by hold state."""
    hold = await _require_hold(session, tenant_id, hold_id)

    if hold.state == HoldState.ACTIVE:
        hold.state = HoldState.RELEASED
        hold.resolved_at = datetime.now()
        session.add(hold)
        await session.commit()
    elif hold.state == HoldState.CAPTURED:
        raise HoldStateError(f"hold {hold.id} is captured and cannot be released")
    # RELEASED already → idempotent no-op replay.

    balance = await available_balance(session, tenant_id, hold.account_id)
    posted = balance.posted if balance else 0
    available = balance.available if balance else 0
    return _to_response(hold, posted, available)


async def _require_account(
    session: AsyncSession, tenant_id: str, account_id: object
) -> Account:
    account = await session.get(Account, account_id)
    if account is None or account.tenant_id != tenant_id or not account.is_open:
        raise InsufficientFundsError(f"account {account_id} not found or closed")
    return account


async def _require_hold(
    session: AsyncSession, tenant_id: str, hold_id: object
) -> Hold:
    hold = await session.get(Hold, hold_id)
    if hold is None or hold.tenant_id != tenant_id:
        raise HoldNotFoundError(f"hold {hold_id} not found")
    return hold


def _to_response(hold: Hold, posted: int, available: int) -> HoldResponse:
    return HoldResponse(
        id=hold.id,
        account_id=hold.account_id,
        amount=hold.amount,
        state=hold.state,
        expires_at=hold.expires_at,
        captured_transaction_id=hold.captured_transaction_id,
        captured_amount=hold.captured_amount,
        posted_balance=posted,
        available_balance=available,
    )
