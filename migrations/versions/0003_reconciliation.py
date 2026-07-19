"""Reconciliation tables.

Revision ID: 0003_reconciliation
Revises: 0002_balance_trigger
Create Date: 2026-05-21
"""

from __future__ import annotations

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = "0003_reconciliation"
down_revision = "0002_balance_trigger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create statement import/line and exception tables."""
    op.create_table(
        "statement_imports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sqlmodel.sql.sqltypes.AutoString(), index=True),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("accounts.id")),
        sa.Column("file_hash", sqlmodel.sql.sqltypes.AutoString(), index=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "statement_lines",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("import_id", sa.Uuid(), sa.ForeignKey("statement_imports.id"), index=True),
        sa.Column("amount", sa.BigInteger()),
        sa.Column("value_date", sa.Date()),
        sa.Column("external_ref", sqlmodel.sql.sqltypes.AutoString(), server_default=""),
        sa.Column("matched_posting_id", sa.Uuid(), nullable=True),
    )
    op.create_table(
        "reconciliation_exceptions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("line_id", sa.Uuid(), sa.ForeignKey("statement_lines.id")),
        sa.Column("kind", sqlmodel.sql.sqltypes.AutoString()),
        sa.Column("resolved", sa.Boolean(), server_default=sa.false()),
    )


def downgrade() -> None:
    """Drop reconciliation tables."""
    op.drop_table("reconciliation_exceptions")
    op.drop_table("statement_lines")
    op.drop_table("statement_imports")
