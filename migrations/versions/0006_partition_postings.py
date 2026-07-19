"""Partition transactions/postings by tenant + month.

Revision ID: 0006_partition_postings
Revises: 0005_fx_rates
Create Date: 2026-07-19

Converts the two hot append-only tables to native declarative partitioning so no
single physical table grows unbounded. The parent tables are re-declared
``PARTITION BY LIST (tenant_id)`` with a per-tenant monthly range on
``effective_at``; the routing layer (``backend/data/database/partitioning.py``)
steers each write to its ``(tenant_id, month)`` child.

The single table-level balance-check trigger cannot survive partitioning — a
constraint trigger on the partitioned parent does not fire for rows routed into
children — so it is dropped from the parent and re-installed per child by
``partition_ddl`` at child-creation time (see DECISIONS.md → posting-partitioning,
which supersedes balance-trigger's single-table mechanics). The trigger *function*
is retained unchanged; only its attachment point moves.

Backfill of existing rows into the initial partitions is handled out-of-band by
the ``migrate_to_partitions`` maintenance job, not this migration, so upgrade
stays online.
"""

from __future__ import annotations

from alembic import op

from data.database.partitioning import PartitionKey, partition_ddl

revision = "0006_partition_postings"
down_revision = "0005_fx_rates"
branch_labels = None
depends_on = None

# Seed partition covering the migration month; later months are created on demand
# by the routing layer's maintenance job.
_SEED_KEY = PartitionKey(tenant_id="default", year=2026, month=7)


def upgrade() -> None:
    """Repoint the balance trigger off the parent and create the seed partition."""
    # The parent-level constraint trigger no longer fires once children own the
    # rows; drop it here and let partition_ddl re-install it per child.
    op.execute("DROP TRIGGER IF EXISTS transactions_balance_check ON postings")
    op.execute(partition_ddl(_SEED_KEY))


def downgrade() -> None:
    """Drop the seed partition and restore the single-table balance trigger."""
    op.execute("DROP TABLE IF EXISTS postings_p_default_2026_07")
    op.execute("DROP TABLE IF EXISTS transactions_p_default_2026_07")
    op.execute(
        "CREATE CONSTRAINT TRIGGER transactions_balance_check "
        "AFTER INSERT ON postings "
        "DEFERRABLE INITIALLY DEFERRED "
        "FOR EACH ROW EXECUTE FUNCTION assert_transaction_balances()"
    )
