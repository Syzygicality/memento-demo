"""Read-only response shapes for the admin/audit surface."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class JournalEntry(BaseModel):
    """One posting against an account, with its parent transaction's context."""

    posting_id: uuid.UUID
    transaction_id: uuid.UUID
    amount: int
    effective_at: datetime
    created_at: datetime
    memo: str
    corrects_id: uuid.UUID | None


class AccountJournalResponse(BaseModel):
    """A page of an account's append-only posting history, oldest first."""

    account_id: uuid.UUID
    entries: list[JournalEntry]
    next_cursor: datetime | None
