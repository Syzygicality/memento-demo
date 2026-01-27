"""Transaction and Posting tables — the append-only core.

A ``Transaction`` groups two or more ``Posting`` rows that MUST sum to zero. That
invariant is enforced by a deferred constraint trigger installed by Alembic
(``transactions_balance_check``), not only by the service layer, so a bug or a
raw SQL write can never leave an unbalanced transaction committed (see
DECISIONS.md → balance-trigger and append-only-ledger).

Neither table is ever updated or deleted in normal operation. A correction is a
new, compensating transaction that references the original via ``corrects_id``.
Postings carry an ``effective_at`` distinct from ``created_at`` so a backdated
entry is representable without mutating history.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlmodel import Field, SQLModel


class Transaction(SQLModel, table=True):
    """A balanced set of postings committed atomically."""

    __tablename__ = "transactions"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    tenant_id: str = Field(index=True)
    memo: str = Field(default="")
    # Set when this transaction reverses/adjusts an earlier one.
    corrects_id: uuid.UUID | None = Field(default=None, foreign_key="transactions.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now())


class Posting(SQLModel, table=True):
    """One signed leg of a transaction against a single account."""

    __tablename__ = "postings"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    transaction_id: uuid.UUID = Field(foreign_key="transactions.id", index=True)
    account_id: uuid.UUID = Field(foreign_key="accounts.id", index=True)
    # Signed minor units. Positive increases the account's normal-balance side.
    amount: int
    # When the entry economically takes effect; may predate created_at.
    effective_at: datetime = Field(index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now())
