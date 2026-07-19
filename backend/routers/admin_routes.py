"""Admin & audit surface — read-only endpoints over the append-only history.

Seeds the `admin` feature hub (roadmap item 12), extending the idempotency
inspection endpoint (item 13). Everything here is a plain read; no endpoint in
this router may mutate ledger state.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import SessionDep, TenantDep
from schemas.admin_schemas import AccountJournalResponse, JournalEntry
from services.admin_service import DEFAULT_PAGE_SIZE, account_journal

router = APIRouter()


@router.get("/accounts/{account_id}/journal", response_model=AccountJournalResponse)
async def get_account_journal_endpoint(
    account_id: uuid.UUID,
    after: datetime | None = Query(default=None),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=200),
    tenant_id: str = TenantDep,
    session: AsyncSession = SessionDep,
) -> AccountJournalResponse:
    """Return a page of an account's postings, oldest first, for support/audit."""
    rows = await account_journal(session, tenant_id, account_id, after=after, limit=limit)
    if rows is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")

    entries = [
        JournalEntry(
            posting_id=row.posting_id,
            transaction_id=row.transaction_id,
            amount=row.amount,
            effective_at=row.effective_at,
            created_at=row.created_at,
            memo=row.memo,
            corrects_id=row.corrects_id,
        )
        for row in rows
    ]
    next_cursor = entries[-1].effective_at if len(entries) == limit else None
    return AccountJournalResponse(
        account_id=account_id, entries=entries, next_cursor=next_cursor
    )
