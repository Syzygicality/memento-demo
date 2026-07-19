"""Account API shapes."""

from __future__ import annotations

import uuid

from pydantic import BaseModel

from data.tables.accounts import NormalBalance
from money.types import Currency


class OpenAccountRequest(BaseModel):
    """Open a new account under a dotted path."""

    path: str
    name: str
    normal_balance: NormalBalance
    currency: Currency


class AccountResponse(BaseModel):
    """An account plus its current materialized balance."""

    id: uuid.UUID
    path: str
    name: str
    normal_balance: NormalBalance
    currency: Currency
    balance: int
    is_open: bool
