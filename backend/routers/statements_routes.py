"""Statement endpoints — streamed CSV export."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import SessionDep, TenantDep
from services.statements_service import stream_statement

router = APIRouter()


@router.get("/{account_id}.csv")
async def statement_csv(
    account_id: uuid.UUID,
    start: datetime,
    end: datetime,
    tenant_id: str = TenantDep,
    session: AsyncSession = SessionDep,
) -> StreamingResponse:
    """Stream an account statement as CSV over the [start, end) window."""

    async def rows() -> AsyncIterator[str]:
        yield "effective_at,amount,running_balance\n"
        async for r in stream_statement(session, account_id, start, end):
            yield f"{r.effective_at.isoformat()},{r.amount},{r.running_balance}\n"

    return StreamingResponse(rows(), media_type="text/csv")
