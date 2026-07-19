"""Holds (authorizations).

Revision ID: 0004_holds
Revises: 0003_reconciliation
Create Date: 2026-07-19

Adds the ``holds`` table backing two-phase money movement. A hold is a
reservation row, not a posting — it never touches ``postings``/``transactions``,
so the append-only ledger and the balance trigger are untouched (see DECISIONS.md
→ hold-is-reservation-not-posting). An account's available balance is computed as
posted minus active, unexpired holds, so the index on
``(account_id, state, expires_at)`` keeps that live sum cheap.
"""

from __future__ import annotations

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = "0004_holds"
down_revision = "0003_reconciliation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the holds table and the index backing the available-balance sum."""
    op.create_table(
        "holds",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sqlmodel.sql.sqltypes.AutoString(), index=True),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("accounts.id"), index=True),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("state", sqlmodel.sql.sqltypes.AutoString(), server_default="active"),
        sa.Column("memo", sqlmodel.sql.sqltypes.AutoString(), server_default=""),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "captured_transaction_id",
            sa.Uuid(),
            sa.ForeignKey("transactions.id"),
            nullable=True,
        ),
        sa.Column("captured_amount", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    # The available-balance query filters active, unexpired holds per account.
    op.create_index(
        "ix_holds_account_state_expiry",
        "holds",
        ["account_id", "state", "expires_at"],
    )


def downgrade() -> None:
    """Drop the holds table and its index."""
    op.drop_index("ix_holds_account_state_expiry", table_name="holds")
    op.drop_table("holds")
