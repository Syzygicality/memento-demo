"""Unit tests for the posting engine's core invariant.

These exercise the balance validation that runs *before* any database work, so
they need no Postgres. The full atomic-write path (snapshot folding, the deferred
DB trigger) is covered by the integration test in
``test_transfers_idempotency.py``, which requires a real database.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from money.types import Minor
from services.postings_engine import PostingSpec, UnbalancedTransactionError, post_transaction


class _NeverTouchedSession:
    """A session the engine must never reach because validation fails first."""

    def add(self, _obj: object) -> None:  # pragma: no cover - must not run
        raise AssertionError("engine touched the session on an invalid transaction")


def _spec(amount: int) -> PostingSpec:
    return PostingSpec(uuid.uuid4(), Minor(amount), datetime(2026, 6, 1))


async def test_single_leg_is_rejected() -> None:
    with pytest.raises(UnbalancedTransactionError):
        await post_transaction(_NeverTouchedSession(), "acme", [_spec(100)])  # type: ignore[arg-type]


async def test_nonzero_sum_is_rejected() -> None:
    with pytest.raises(UnbalancedTransactionError):
        await post_transaction(
            _NeverTouchedSession(),  # type: ignore[arg-type]
            "acme",
            [_spec(100), _spec(-90)],
        )
