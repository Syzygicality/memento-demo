"""FX rates (cross-currency conversion).

Revision ID: 0005_fx_rates
Revises: 0004_holds
Create Date: 2026-07-19

Adds the append-only ``fx_rates`` table backing cross-currency transfers. A
conversion resolves the effective rate for its pair at its ``effective_at`` and
routes value through per-currency conversion accounts, so the ledger's
per-transaction balance trigger is untouched — each leg is single-currency (see
DECISIONS.md → fx-conversion-accounts, which supersedes currency-fixed-per-account).
The index on ``(base_currency, quote_currency, effective_at)`` keeps the
"most-recent effective rate for this pair" lookup a single index scan.
"""

from __future__ import annotations

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = "0005_fx_rates"
down_revision = "0004_holds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the append-only fx_rates table and its pair/effective-at index."""
    op.create_table(
        "fx_rates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sqlmodel.sql.sqltypes.AutoString(), server_default="", index=True),
        sa.Column("base_currency", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("quote_currency", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("rate", sa.Numeric(20, 10), nullable=False),
        sa.Column("source", sqlmodel.sql.sqltypes.AutoString(), server_default="manual"),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    # "Latest effective rate for this pair at or before T" — one index scan.
    op.create_index(
        "ix_fx_rates_pair_effective",
        "fx_rates",
        ["base_currency", "quote_currency", "effective_at"],
    )


def downgrade() -> None:
    """Drop the fx_rates table and its index."""
    op.drop_index("ix_fx_rates_pair_effective", table_name="fx_rates")
    op.drop_table("fx_rates")
