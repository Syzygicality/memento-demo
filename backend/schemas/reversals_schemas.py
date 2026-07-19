"""Reversal request/response shapes."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class ReverseTransactionRequest(BaseModel):
    """Reverse ``transaction_id`` in full with a new compensating transaction."""

    memo: str = ""


class ReversalResponse(BaseModel):
    """The compensating transaction created to reverse an earlier one."""

    id: uuid.UUID
    corrects_id: uuid.UUID
    memo: str
    created_at: datetime
