"""Import every table module so Alembic autogenerate sees the full metadata.

A new table is invisible to ``--autogenerate`` until its module is imported
here — that is deliberate: adding a table is a decision, and this file is the one
place that records the ledger's full schema surface.
"""

from __future__ import annotations

from data.tables import (  # noqa: F401
    accounts,
    balances,
    idempotency,
    reconciliation,
    transactions,
)
