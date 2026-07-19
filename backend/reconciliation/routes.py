"""Reconciliation endpoints (import + exception listing)."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import SessionDep, TenantDep
from data.tables.reconciliation import ReconciliationException, StatementImport

router = APIRouter()


@router.get("/imports")
async def list_imports(
    tenant_id: str = TenantDep,
    session: AsyncSession = SessionDep,
) -> list[dict[str, str]]:
    """List this tenant's statement imports."""
    rows = await session.execute(
        select(StatementImport).where(StatementImport.tenant_id == tenant_id)
    )
    return [
        {"id": str(i.id), "account_id": str(i.account_id), "file_hash": i.file_hash}
        for i in rows.scalars().all()
    ]


@router.get("/exceptions")
async def list_exceptions(
    resolved: bool = False,
    tenant_id: str = TenantDep,
    session: AsyncSession = SessionDep,
) -> list[dict[str, str]]:
    """List unmatched/ambiguous statement lines awaiting resolution."""
    rows = await session.execute(
        select(ReconciliationException).where(
            ReconciliationException.resolved == resolved
        )
    )
    return [{"id": str(e.id), "kind": e.kind, "line_id": str(e.line_id)} for e in rows.scalars().all()]
