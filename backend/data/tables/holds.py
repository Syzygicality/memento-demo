"""Hold (authorization) table — a reservation, not a posting.

A hold reserves funds on an account for later capture or release, the first half
of a two-phase money movement (authorize, then capture/void — the card-auth
model). A hold is deliberately **not** a posting: it never touches the
append-only ledger and never moves money. Only a *capture* writes a balanced
transaction. Keeping a hold as a separate reservation row is what lets the ledger
stay append-only and every transaction still balance to zero — a reservation is
not yet a money movement (see DECISIONS.md → hold-is-reservation-not-posting).

An account's spendable balance is therefore ``available = posted - Σ active
holds``; the ``posted`` snapshot (``account_balances``) is unchanged, and holds
are subtracted live at read time (see DECISIONS.md → available-vs-posted-split).
A hold stops counting against ``available`` the moment it leaves the ``ACTIVE``
state or its ``expires_at`` passes — expiry frees the reservation without any
sweep having to run (see DECISIONS.md → hold-expiry-frees-on-read).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlmodel import Field, SQLModel


class HoldState(StrEnum):
    """The lifecycle state of a hold."""

    # Reserving funds; counts against available until it expires.
    ACTIVE = "active"
    # Converted into a real transaction; no longer reserves.
    CAPTURED = "captured"
    # Voided before capture; the reservation is freed.
    RELEASED = "released"


class Hold(SQLModel, table=True):
    """A reservation of funds on one account, scoped to one tenant."""

    __tablename__ = "holds"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    tenant_id: str = Field(index=True)
    # The account whose available balance this hold reserves against.
    account_id: uuid.UUID = Field(foreign_key="accounts.id", index=True)
    # Positive minor units reserved; never negative, never a float.
    amount: int
    state: HoldState = Field(default=HoldState.ACTIVE, index=True)
    memo: str = Field(default="")
    # A hold stops counting against available once this instant passes, even if
    # it is still ACTIVE and no sweep has reclaimed it.
    expires_at: datetime = Field(index=True)
    # Set when the hold is captured into a real transaction.
    captured_transaction_id: uuid.UUID | None = Field(
        default=None, foreign_key="transactions.id"
    )
    # The amount actually captured (<= amount); the remainder is released.
    captured_amount: int | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now())
    resolved_at: datetime | None = Field(default=None)
