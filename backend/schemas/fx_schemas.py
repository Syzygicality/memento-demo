"""FX request/response shapes."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from money.types import Currency


class QuoteRequest(BaseModel):
    """Ask for the amount ``amount`` (source minor units) would convert to."""

    source_currency: Currency
    target_currency: Currency
    amount: int = Field(gt=0, description="source minor units; must be positive")
    # Quote as of this instant; defaults to now in the service if omitted.
    as_of: datetime | None = None


class QuoteResponse(BaseModel):
    """A non-binding conversion quote plus the rate provenance used."""

    source_currency: Currency
    target_currency: Currency
    source_amount: int
    target_amount: int
    rate: Decimal
    rate_source: str
    rate_id: uuid.UUID | None = None
    effective_at: datetime


class UpsertRateRequest(BaseModel):
    """Publish a new effective rate for an ordered pair (append-only)."""

    base_currency: Currency
    quote_currency: Currency
    rate: Decimal = Field(gt=0, description="target-per-source, major units")
    source: str = "manual"
    effective_at: datetime | None = None
