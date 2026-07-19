"""Transactional outbox.

Revision ID: 0007_outbox
Revises: 0006_partition_postings
Create Date: 2026-07-19

Adds ``outbox_events``, written by the posting engine in the same transaction as
every posted transaction (see DECISIONS.md → outbox-same-transaction). The table
is intentionally unpartitioned and untouched by the balance trigger: it never
mutates a posting or a balance, only records that one happened.
"""

from __future__ import annotations

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = "0007_outbox"
down_revision = "0006_partition_postings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the outbox_events table and the indexes backing dispatch order."""
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sqlmodel.sql.sqltypes.AutoString(), index=True),
        sa.Column(
            "transaction_id", sa.Uuid(), sa.ForeignKey("transactions.id"), index=True
        ),
        sa.Column(
            "event_type",
            sqlmodel.sql.sqltypes.AutoString(),
            server_default="transaction.posted",
        ),
        sa.Column("payload", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "status", sqlmodel.sql.sqltypes.AutoString(), server_default="pending"
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Dispatch and listing both scan (tenant, status) ordered by created_at.
    op.create_index(
        "ix_outbox_tenant_status_created",
        "outbox_events",
        ["tenant_id", "status", "created_at"],
    )


def downgrade() -> None:
    """Drop the outbox_events table and its index."""
    op.drop_index("ix_outbox_tenant_status_created", table_name="outbox_events")
    op.drop_table("outbox_events")
