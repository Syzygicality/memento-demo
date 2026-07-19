"""FX endpoints — quote a conversion and publish rates.

These are read/administrative surfaces. Actual money movement across currencies
happens inside the transfer path, which routes through conversion accounts (see
``fx.service``); a quote here is deliberately non-binding — the transfer resolves
the rate again at execution time so a stale quote can never lock in a price.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import SessionDep, TenantDep
from data.tables.fx_rates import FxRate
from services.fx_rates import RateUnavailableError, resolve_rate
from schemas.fx_schemas import QuoteRequest, QuoteResponse, UpsertRateRequest
from money.types import convert

router = APIRouter()


@router.post("/quote", response_model=QuoteResponse)
async def quote_endpoint(
    req: QuoteRequest,
    tenant_id: str = TenantDep,
    session: AsyncSession = SessionDep,
) -> QuoteResponse:
    """Quote what ``amount`` in the source currency converts to. Non-binding."""
    as_of = req.as_of or datetime.now()
    try:
        rate = await resolve_rate(session, req.source_currency, req.target_currency, as_of)
    except RateUnavailableError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    target = convert(req.amount, req.source_currency, req.target_currency, rate.rate)  # type: ignore[arg-type]
    return QuoteResponse(
        source_currency=req.source_currency,
        target_currency=req.target_currency,
        source_amount=req.amount,
        target_amount=int(target),
        rate=rate.rate,
        rate_source=rate.source,
        rate_id=rate.rate_id,  # type: ignore[arg-type]
        effective_at=rate.effective_at,
    )


@router.post("/rates", status_code=status.HTTP_201_CREATED)
async def upsert_rate_endpoint(
    req: UpsertRateRequest,
    tenant_id: str = TenantDep,
    session: AsyncSession = SessionDep,
) -> dict[str, str]:
    """Publish a new effective rate. Append-only: this never updates a prior row."""
    row = FxRate(
        tenant_id=tenant_id,
        base_currency=req.base_currency,
        quote_currency=req.quote_currency,
        rate=req.rate,
        source=req.source,
        effective_at=req.effective_at or datetime.now(),
    )
    session.add(row)
    await session.commit()
    return {"id": str(row.id)}
