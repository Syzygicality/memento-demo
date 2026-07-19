"""Rate resolution — the read side of the FX rate table.

A conversion asks this module a single question: *what rate was effective for
this pair at this instant?* The answer is the most recent ``fx_rates`` row for
the pair whose ``effective_at`` is at or before the requested time. Because rates
are append-only, that lookup is deterministic and a historical conversion always
resolves the same row it originally saw.

Rates are quoted in one direction and derived in the other by reciprocal, so an
operator only maintains one side of each pair. An identity pair (USD→USD) is
always rate 1 and never hits the table.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data.tables.fx_rates import FxRate
from money.types import Currency

ONE = Decimal(1)


class RateUnavailableError(Exception):
    """No effective rate exists for the requested pair at the requested time."""


@dataclass(frozen=True)
class ResolvedRate:
    """A rate plus the provenance needed to make a conversion auditable."""

    rate: Decimal
    source: str
    rate_id: object | None  # the fx_rates row id, or None for the identity pair
    effective_at: datetime


async def resolve_rate(
    session: AsyncSession,
    base: Currency,
    quote: Currency,
    as_of: datetime,
) -> ResolvedRate:
    """Resolve the effective ``base``→``quote`` rate at ``as_of``.

    Tries the direct pair first, then the reciprocal of the inverse pair, so only
    one direction of each pair needs to be maintained. Raises
    ``RateUnavailableError`` when neither direction has an effective quote.
    """
    if base == quote:
        return ResolvedRate(rate=ONE, source="identity", rate_id=None, effective_at=as_of)

    direct = await _latest(session, base, quote, as_of)
    if direct is not None:
        return ResolvedRate(
            rate=direct.rate,
            source=direct.source,
            rate_id=direct.id,
            effective_at=direct.effective_at,
        )

    inverse = await _latest(session, quote, base, as_of)
    if inverse is not None and inverse.rate != 0:
        return ResolvedRate(
            rate=(ONE / inverse.rate),
            source=f"{inverse.source} (reciprocal)",
            rate_id=inverse.id,
            effective_at=inverse.effective_at,
        )

    raise RateUnavailableError(f"no effective rate for {base}->{quote} at {as_of.isoformat()}")


async def _latest(
    session: AsyncSession, base: Currency, quote: Currency, as_of: datetime
) -> FxRate | None:
    """The most recent effective row for an ordered pair at or before ``as_of``."""
    stmt = (
        select(FxRate)
        .where(
            FxRate.base_currency == base,
            FxRate.quote_currency == quote,
            FxRate.effective_at <= as_of,
        )
        .order_by(FxRate.effective_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
