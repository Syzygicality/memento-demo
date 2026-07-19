"""FX rate table — a point-in-time, provenance-tagged exchange rate.

A conversion never reads a rate out of the air: every cross-currency movement
resolves the *effective* rate for its pair at its ``effective_at`` from this
table, and stores which rate row it used. Rates are append-only like the ledger
itself — a new quote is a new row with a later ``effective_at``, never an
``UPDATE`` of an existing one — so a historical conversion can always be
re-derived from the exact rate it saw (see DECISIONS.md → fx-conversion-accounts).

The ``rate`` is stored as a ``NUMERIC`` (never a float) expressed as
target-per-source major units. ``source`` records where the quote came from
(the provider or ``manual``) so a disputed conversion is auditable back to its
provenance.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlmodel import Field, SQLModel

from money.types import Currency


class FxRate(SQLModel, table=True):
    """One quoted rate for an ordered currency pair, valid from ``effective_at``."""

    __tablename__ = "fx_rates"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    # Rates are global today; tenant_id is carried for a future per-tenant desk.
    tenant_id: str = Field(default="", index=True)
    base_currency: Currency = Field(index=True)
    quote_currency: Currency = Field(index=True)
    # target-per-source, major units; NUMERIC so it is never a float.
    rate: Decimal = Field(max_digits=20, decimal_places=10)
    # Provenance: the provider name, or "manual" for an operator-entered quote.
    source: str = Field(default="manual")
    # The quote is the effective rate for its pair from this instant forward,
    # until a later row supersedes it. Append-only; never updated in place.
    effective_at: datetime = Field(index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now())
