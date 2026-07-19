"""Observability: structured logs, request metrics, and lightweight tracing.

Per-request tracing rides on the request id already stamped by
``RequestContextMiddleware`` (see DECISIONS.md → request-context stays
authoritative for tenant/request id). This module only adds timing, a log line
per request, and in-process counters for money-movement endpoints, plus a
balance-drift check that compares the materialized snapshot against
``recompute`` (see DECISIONS.md → balance-drift-snapshot-vs-recompute).
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp
from sqlalchemy.ext.asyncio import AsyncSession

from services.balances_service import current_balance, recompute

logger = logging.getLogger("ledger.observability")


@dataclass
class _Metrics:
    """In-process counters. Good enough for a demo; a real deploy exports these
    to a metrics backend instead of holding them in memory."""

    request_count: int = 0
    request_seconds_total: float = 0.0
    by_status: dict[int, int] = field(default_factory=dict)

    def record(self, status_code: int, duration: float) -> None:
        self.request_count += 1
        self.request_seconds_total += duration
        self.by_status[status_code] = self.by_status.get(status_code, 0) + 1


metrics = _Metrics()


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Time each request, log it with its trace/request id, and update metrics."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        trace_id = request.headers.get("x-trace-id") or uuid.uuid4().hex
        request.state.trace_id = trace_id
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start

        metrics.record(response.status_code, duration)
        response.headers["x-trace-id"] = trace_id

        logger.info(
            "request completed",
            extra={
                "trace_id": trace_id,
                "request_id": getattr(request.state, "request_id", None),
                "tenant_id": getattr(request.state, "tenant_id", None),
                "path": request.url.path,
                "method": request.method,
                "status_code": response.status_code,
                "duration_ms": round(duration * 1000, 2),
            },
        )
        return response


async def check_balance_drift(
    session: AsyncSession, tenant_id: str, account_id: uuid.UUID
) -> int | None:
    """Return the drift (snapshot minus recompute) for an account, or None if
    the account has no snapshot yet. A non-zero result is an alertable event —
    it means the materialized balance and the posting ledger disagree."""
    snapshot = await current_balance(session, tenant_id, account_id)
    if snapshot is None:
        return None
    exact = await recompute(session, account_id)
    drift = snapshot - exact
    if drift != 0:
        logger.warning(
            "balance drift detected",
            extra={
                "tenant_id": tenant_id,
                "account_id": str(account_id),
                "snapshot": snapshot,
                "recomputed": exact,
                "drift": drift,
            },
        )
    return drift
