"""Router and middleware wiring.

`main.py` stays intentionally minimal; all composition happens here so there is
one place that knows the full shape of the app. New endpoints are added by
registering a router in ``setup_routes`` — never by expanding ``main.py`` (see
DECISIONS.md → thin-entrypoint).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.accounts_routes import router as accounts_router
from api.middleware.request_context import RequestContextMiddleware
from routers.balances_routes import router as balances_router
from config.config import settings
from routers.reconciliation_routes import router as reconciliation_router
from routers.statements_routes import router as statements_router
from routers.transfers_routes import router as transfers_router

API_PREFIX = "/api/v1"


def setup_middlewares(app: FastAPI) -> None:
    """Register middleware in a fixed, load-bearing order.

    CORS is outermost; the request-context middleware (tenant + request id) runs
    inside it so every downstream handler and log line has a resolved tenant.
    Reordering these changes which requests are authenticated, so the order is
    deliberate.
    """
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestContextMiddleware)


def setup_routes(app: FastAPI) -> None:
    """Mount every feature router under the versioned prefix."""
    app.include_router(accounts_router, prefix=f"{API_PREFIX}/accounts", tags=["accounts"])
    app.include_router(transfers_router, prefix=f"{API_PREFIX}/transfers", tags=["transfers"])
    app.include_router(balances_router, prefix=f"{API_PREFIX}/balances", tags=["balances"])
    app.include_router(
        reconciliation_router,
        prefix=f"{API_PREFIX}/reconciliation",
        tags=["reconciliation"],
    )
    app.include_router(statements_router, prefix=f"{API_PREFIX}/statements", tags=["statements"])
