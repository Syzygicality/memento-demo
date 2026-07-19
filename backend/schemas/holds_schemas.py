"""Hold request/response shapes."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from data.tables.holds import HoldState


class PlaceHoldRequest(BaseModel):
    """Reserve ``amount`` minor units on an account for later capture."""

    account_id: uuid.UUID
    amount: int = Field(gt=0, description="minor units to reserve; must be positive")
    memo: str = ""
    # Optional explicit expiry; defaults to now + the configured TTL if omitted.
    expires_at: datetime | None = None


class CaptureHoldRequest(BaseModel):
    """Capture a hold into a real transfer to ``destination_account_id``."""

    destination_account_id: uuid.UUID
    # Capture up to the held amount; omit to capture the full hold. The
    # uncaptured remainder is released back to the source's available balance.
    amount: int | None = Field(default=None, gt=0)
    memo: str = ""


class HoldResponse(BaseModel):
    """A hold's current state plus the source account's resulting balances."""

    id: uuid.UUID
    account_id: uuid.UUID
    amount: int
    state: HoldState
    expires_at: datetime
    captured_transaction_id: uuid.UUID | None = None
    captured_amount: int | None = None
    # The source account's balances after the operation.
    posted_balance: int
    available_balance: int
