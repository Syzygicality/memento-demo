"""Statement import.

Imports are idempotent by the file's content hash: a ``StatementImport`` row is
keyed by ``file_hash``, so re-uploading the same file returns the existing import
instead of duplicating its lines (see DECISIONS.md →
reconciliation-idempotent-import). Parsing is tolerant per line — a malformed row
is collected as a parse error and skipped, never aborting the whole file.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data.tables.reconciliation import StatementImport, StatementLine


@dataclass
class ParsedLine:
    """One normalized statement line prior to persistence."""

    amount: int
    value_date: date
    external_ref: str = ""


@dataclass
class ImportResult:
    """Outcome of an import attempt."""

    import_id: uuid.UUID
    created: bool
    line_count: int
    parse_errors: list[str] = field(default_factory=list)


def file_hash(raw: bytes) -> str:
    """Content hash used as the idempotency key for an import."""
    return hashlib.sha256(raw).hexdigest()


async def import_statement(
    session: AsyncSession,
    tenant_id: str,
    account_id: uuid.UUID,
    raw: bytes,
    lines: list[ParsedLine],
) -> ImportResult:
    """Persist a statement's lines once, keyed by content hash."""
    digest = file_hash(raw)
    existing = await session.execute(
        select(StatementImport).where(
            StatementImport.tenant_id == tenant_id, StatementImport.file_hash == digest
        )
    )
    found = existing.scalars().first()
    if found is not None:
        return ImportResult(found.id, created=False, line_count=0)

    imp = StatementImport(tenant_id=tenant_id, account_id=account_id, file_hash=digest)
    session.add(imp)
    await session.flush()
    for line in lines:
        session.add(
            StatementLine(
                import_id=imp.id,
                amount=line.amount,
                value_date=line.value_date,
                external_ref=line.external_ref,
            )
        )
    await session.commit()
    return ImportResult(imp.id, created=True, line_count=len(lines))
