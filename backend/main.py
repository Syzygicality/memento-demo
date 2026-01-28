"""Ledger API entrypoint.

Intentionally minimal: it constructs the app with the lifespan and delegates all
wiring to ``api.backend_setup``. Do not add routers or middleware here.
"""

from __future__ import annotations

from fastapi import FastAPI

from api.backend_setup import setup_middlewares, setup_routes
from api.lifespan import lifespan

app = FastAPI(title="Ledger", version="0.9.0", lifespan=lifespan)
setup_middlewares(app)
setup_routes(app)


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    """Liveness probe. Does not touch the database."""
    return {"status": "ok"}
