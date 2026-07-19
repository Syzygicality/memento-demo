"""Request dependencies.

`current_tenant` resolves the acting tenant from the request context (set by the
middleware from a signed session token) — never from the request body. A money
endpoint that trusted a body-supplied tenant id would let one tenant post into
another's accounts, so tenant is always taken from the authenticated context
(see DECISIONS.md → tenant-from-auth-context).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from data.database.engine import get_db_session


async def db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped session."""
    async for session in get_db_session():
        yield session


def current_tenant(request: Request) -> str:
    """Return the tenant id resolved by the request-context middleware."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="No tenant in context"
        )
    return tenant_id


TenantDep = Depends(current_tenant)
SessionDep = Depends(db_session)
