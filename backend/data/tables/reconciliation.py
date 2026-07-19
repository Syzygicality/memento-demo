"""Reconciliation tables.

External statements are imported as ``StatementLine`` rows under a
``StatementImport`` keyed by the file's content hash (so re-importing the same
file is a no-op — see DECISIONS.md → reconciliation-idempotent-import). The
matcher links lines to postings deterministically; a line it cannot match becomes
a ``ReconciliationException`` for a human to resolve, and is never auto-adjusted
into the ledger (see DECISIONS.md → reconciliation-exceptions-not-auto).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlmodel import Field, SQLModel


class StatementImport(SQLModel, table=True):
    """One imported external statement file."""

    __tablename__ = "statement_imports"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    tenant_id: str = Field(index=True)
    account_id: uuid.UUID = Field(foreign_key="accounts.id")
    # Content hash; the unique key that makes re-import idempotent.
    file_hash: str = Field(index=True)
    imported_at: datetime = Field(default_factory=lambda: datetime.now())


class StatementLine(SQLModel, table=True):
    """One line from an external statement."""

    __tablename__ = "statement_lines"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    import_id: uuid.UUID = Field(foreign_key="statement_imports.id", index=True)
    amount: int
    value_date: date
    external_ref: str = Field(default="")
    matched_posting_id: uuid.UUID | None = Field(default=None)


class ExceptionKind(StrEnum):
    """Why a line could not be matched."""

    UNMATCHED = "unmatched"
    AMBIGUOUS = "ambiguous"
    AMOUNT_MISMATCH = "amount_mismatch"


class ReconciliationException(SQLModel, table=True):
    """An unresolved statement line awaiting human action."""

    __tablename__ = "reconciliation_exceptions"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    line_id: uuid.UUID = Field(foreign_key="statement_lines.id")
    kind: ExceptionKind
    resolved: bool = Field(default=False)
