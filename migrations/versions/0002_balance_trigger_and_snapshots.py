"""Balance snapshots + the transaction balance-check trigger.

Revision ID: 0002_balance_trigger
Revises: 0001_initial
Create Date: 2026-03-18

Adds ``account_balances`` and installs a DEFERRED constraint trigger that fires
at COMMIT and rejects any transaction whose postings do not sum to zero. The
trigger is deferred so the posting engine can insert the legs one at a time
within a transaction; the sum is only required to be zero at commit. This is the
enforcement point referenced by DECISIONS.md → balance-trigger: the invariant
lives in the database, not only in application code.
"""

from __future__ import annotations

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = "0002_balance_trigger"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


_TRIGGER_FN = """
CREATE OR REPLACE FUNCTION assert_transaction_balances() RETURNS trigger AS $$
DECLARE
    net BIGINT;
BEGIN
    SELECT COALESCE(SUM(amount), 0) INTO net
    FROM postings WHERE transaction_id = NEW.transaction_id;
    IF net <> 0 THEN
        RAISE EXCEPTION 'transaction % is unbalanced (net=%)', NEW.transaction_id, net;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

_TRIGGER = """
CREATE CONSTRAINT TRIGGER transactions_balance_check
AFTER INSERT ON postings
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION assert_transaction_balances();
"""


def upgrade() -> None:
    """Create the snapshot table and the deferred balance trigger."""
    op.create_table(
        "account_balances",
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("accounts.id"), primary_key=True),
        sa.Column("tenant_id", sqlmodel.sql.sqltypes.AutoString(), index=True),
        sa.Column("balance", sa.BigInteger(), server_default="0"),
        sa.Column("version", sa.Integer(), server_default="0"),
        sa.Column("as_of_posting_id", sa.Uuid(), nullable=True),
    )
    op.execute(_TRIGGER_FN)
    op.execute(_TRIGGER)


def downgrade() -> None:
    """Remove the trigger and snapshot table."""
    op.execute("DROP TRIGGER IF EXISTS transactions_balance_check ON postings")
    op.execute("DROP FUNCTION IF EXISTS assert_transaction_balances()")
    op.drop_table("account_balances")
