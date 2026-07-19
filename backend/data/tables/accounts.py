"""Account table.

An account is typed by its **normal balance** (debit or credit). The sign
convention is applied at posting time, not at read time, so a stored posting is
already signed correctly for its account and a balance is a plain sum (see
DECISIONS.md → sign-at-posting-time). Accounts are arranged in a hierarchy via a
materialized ``path`` (e.g. ``assets.cash.operating``) so reports roll up by
prefix without a recursive query (see DECISIONS.md → chart-materialized-path).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlmodel import Field, SQLModel

from money.types import Currency


class NormalBalance(StrEnum):
    """Which side increases the account."""

    DEBIT = "debit"
    CREDIT = "credit"


class Account(SQLModel, table=True):
    """A single ledger account, scoped to one tenant and one currency."""

    __tablename__ = "accounts"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    tenant_id: str = Field(index=True)
    # Dotted materialized path; the last segment is this account's name.
    path: str = Field(index=True)
    name: str
    normal_balance: NormalBalance
    # Currency is fixed at creation and never changed (DECISIONS.md →
    # currency-fixed-per-account).
    currency: Currency
    is_open: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now())
