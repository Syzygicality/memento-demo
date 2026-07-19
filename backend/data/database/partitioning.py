"""Partition routing for the append-only posting core.

``postings`` and ``transactions`` are the hot tables — they grow without bound
because the ledger is append-only (nothing is ever deleted). To keep any one
physical table small enough for its indexes to stay in cache, the two tables are
declared ``PARTITION BY LIST (tenant_id), RANGE (created_at)`` in Alembic, and
every write is steered to the right child partition by the routing layer here.

The routing key is ``(tenant_id, month)``: a tenant's rows for a calendar month
land in a single child. This keeps a tenant's recent activity — the overwhelming
majority of reads and every write — inside one small partition, while cold months
age out into partitions that are rarely touched and cheap to detach or archive.

The balance-check trigger cannot survive as a single table-level trigger once the
parent is partitioned: a constraint trigger on the partitioned parent does not
fire for rows routed into children. It moves to a per-partition trigger installed
by :func:`partition_ddl` whenever a new child is created (see DECISIONS.md →
posting-partitioning, which supersedes balance-trigger's single-table mechanics).

Nothing here issues DDL at runtime — :func:`partition_ddl` returns the SQL for an
Alembic migration to execute. The application only *routes*; Alembic still owns
every ``CREATE``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# Partitioned tables. Both share the same routing key so a transaction and its
# postings always co-locate in the same tenant/month child.
PARTITIONED_TABLES = ("transactions", "postings")


@dataclass(frozen=True)
class PartitionKey:
    """Identifies the child partition a row belongs to."""

    tenant_id: str
    year: int
    month: int

    @property
    def suffix(self) -> str:
        """Table-name suffix, e.g. ``acme_2026_07`` — stable and sortable."""
        safe_tenant = self.tenant_id.replace("-", "_") or "default"
        return f"{safe_tenant}_{self.year:04d}_{self.month:02d}"


def route(tenant_id: str, effective_at: datetime) -> PartitionKey:
    """Resolve the partition a row is written to.

    Routing is by ``effective_at`` (when the entry economically takes effect),
    not ``created_at`` — a backdated posting belongs with the month it affects, so
    period roll-ups read a single contiguous partition rather than fanning out.
    """
    return PartitionKey(tenant_id=tenant_id, year=effective_at.year, month=effective_at.month)


def child_table_name(table: str, key: PartitionKey) -> str:
    """Physical child-partition name for a parent table and routing key."""
    if table not in PARTITIONED_TABLES:
        raise ValueError(f"{table!r} is not a partitioned table")
    return f"{table}_p_{key.suffix}"


def _month_bounds(key: PartitionKey) -> tuple[str, str]:
    """Half-open ``[start, end)`` RFC3339 bounds for a month partition."""
    start = f"{key.year:04d}-{key.month:02d}-01T00:00:00+00:00"
    end_year, end_month = (key.year + 1, 1) if key.month == 12 else (key.year, key.month + 1)
    end = f"{end_year:04d}-{end_month:02d}-01T00:00:00+00:00"
    return start, end


def partition_ddl(key: PartitionKey) -> str:
    """SQL that creates one tenant/month child for every partitioned table.

    Returned to an Alembic migration to execute — never run at request time. Each
    child re-installs the deferred balance-check trigger locally, because the
    parent-level constraint trigger does not fire for rows routed into children.
    """
    start, end = _month_bounds(key)
    stmts: list[str] = []
    for table in PARTITIONED_TABLES:
        child = child_table_name(table, key)
        stmts.append(
            f"CREATE TABLE IF NOT EXISTS {child} PARTITION OF {table} "
            f"FOR VALUES FROM ('{start}') TO ('{end}');"
        )
    # Re-attach the balance trigger to the postings child (see module docstring).
    postings_child = child_table_name("postings", key)
    stmts.append(
        f"CREATE CONSTRAINT TRIGGER {postings_child}_balance_check "
        f"AFTER INSERT ON {postings_child} "
        f"DEFERRABLE INITIALLY DEFERRED "
        f"FOR EACH ROW EXECUTE FUNCTION assert_transaction_balances();"
    )
    return "\n".join(stmts)
