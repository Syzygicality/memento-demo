"""Background sweep of expired idempotency records.

Promotes the sweep from an ad-hoc helper to a scheduled job: it runs on a fixed
interval for the life of the process, deleting records older than the retention
window and emitting metrics on reclaimed vs retained keys (builds on
DECISIONS.md → idempotency-sweep-min-age).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from data.tables.idempotency import IdempotencyRecord

logger = logging.getLogger("ledger.idempotency_sweeper")

DEFAULT_MIN_AGE = timedelta(hours=24)
DEFAULT_INTERVAL_SECONDS = 3600


@dataclass(frozen=True)
class SweepResult:
    """Counts from a single sweep pass."""

    reclaimed: int
    retained: int


async def sweep_once(session: AsyncSession, min_age: timedelta = DEFAULT_MIN_AGE) -> SweepResult:
    """Delete idempotency records older than ``min_age`` and report the tally."""
    cutoff = datetime.now() - min_age

    reclaimed_result = await session.execute(
        delete(IdempotencyRecord)
        .where(IdempotencyRecord.created_at < cutoff)
        .returning(IdempotencyRecord.key)
    )
    reclaimed = len(reclaimed_result.all())

    retained = await session.scalar(select(func.count()).select_from(IdempotencyRecord))
    await session.commit()

    logger.info("idempotency sweep: reclaimed=%d retained=%d", reclaimed, retained or 0)
    return SweepResult(reclaimed=reclaimed, retained=retained or 0)


async def run_forever(
    session_factory,
    min_age: timedelta = DEFAULT_MIN_AGE,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
) -> None:
    """Sweep on a fixed interval until cancelled (driven by the app lifespan)."""
    while True:
        try:
            async with session_factory() as session:
                await sweep_once(session, min_age=min_age)
        except Exception:
            logger.exception("idempotency sweep pass failed")
        await asyncio.sleep(interval_seconds)
