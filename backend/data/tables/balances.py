"""Materialized balance snapshot.

One row per account holding its current balance in minor units. The row is
updated inside the *same transaction* that writes the postings, so a committed
balance can never disagree with the postings that produced it (see DECISIONS.md
→ balance-snapshot, which superseded the original compute-on-read approach).

``as_of_posting_id`` and ``version`` form a watermark: a reader that has seen a
newer posting than the snapshot's watermark knows the snapshot is stale and can
fall back to summation for that account.
"""

from __future__ import annotations

import uuid

from sqlmodel import Field, SQLModel


class AccountBalance(SQLModel, table=True):
    """Current balance for one account (minor units)."""

    __tablename__ = "account_balances"

    account_id: uuid.UUID = Field(primary_key=True, foreign_key="accounts.id")
    tenant_id: str = Field(index=True)
    balance: int = Field(default=0)
    # Monotonic counter bumped on every update; cheap staleness check.
    version: int = Field(default=0)
    # The last posting folded into this snapshot.
    as_of_posting_id: uuid.UUID | None = Field(default=None)
