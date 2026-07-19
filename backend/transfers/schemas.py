"""Transfer request/response shapes."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TransferRequest(BaseModel):
    """Move ``amount`` minor units from one account to another."""

    source_account_id: uuid.UUID
    destination_account_id: uuid.UUID
    amount: int = Field(gt=0, description="minor units; must be positive")
    memo: str = ""
    # Optional backdating; defaults to now in the service if omitted.
    effective_at: datetime | None = None


class TransferResponse(BaseModel):
    """The committed transaction id and resulting source balance."""

    transaction_id: uuid.UUID
    source_balance: int
    destination_balance: int
