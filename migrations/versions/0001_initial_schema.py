"""Initial ledger schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-01-30

Creates the core tables. The balance-check trigger is intentionally NOT here — it
lands in 0002 alongside the account_balances snapshot, so the two invariants
(transactions balance; snapshots track postings) are introduced together.
"""

from __future__ import annotations

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create accounts, transactions, postings, and idempotency tables."""
    op.create_table(
        "accounts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sqlmodel.sql.sqltypes.AutoString(), index=True),
        sa.Column("path", sqlmodel.sql.sqltypes.AutoString(), index=True),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString()),
        sa.Column("normal_balance", sqlmodel.sql.sqltypes.AutoString()),
        sa.Column("currency", sqlmodel.sql.sqltypes.AutoString()),
        sa.Column("is_open", sa.Boolean(), server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "transactions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sqlmodel.sql.sqltypes.AutoString(), index=True),
        sa.Column("memo", sqlmodel.sql.sqltypes.AutoString(), server_default=""),
        sa.Column("corrects_id", sa.Uuid(), sa.ForeignKey("transactions.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "postings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("transaction_id", sa.Uuid(), sa.ForeignKey("transactions.id"), index=True),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("accounts.id"), index=True),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "idempotency_records",
        sa.Column("tenant_id", sqlmodel.sql.sqltypes.AutoString(), primary_key=True),
        sa.Column("endpoint", sqlmodel.sql.sqltypes.AutoString(), primary_key=True),
        sa.Column("key", sqlmodel.sql.sqltypes.AutoString(), primary_key=True),
        sa.Column("request_fingerprint", sqlmodel.sql.sqltypes.AutoString()),
        sa.Column("response_json", sqlmodel.sql.sqltypes.AutoString()),
        sa.Column("status_code", sa.Integer(), server_default="200"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
    )


def downgrade() -> None:
    """Drop the core tables."""
    op.drop_table("idempotency_records")
    op.drop_table("postings")
    op.drop_table("transactions")
    op.drop_table("accounts")
