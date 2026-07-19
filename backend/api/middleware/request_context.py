"""Request-context middleware.

Resolves the tenant from a signed session token and stamps a request id onto
``request.state`` and the log context. Runs inside CORS but before any route so
every handler and log line downstream has a tenant. Verification failures leave
``tenant_id`` unset (the deps layer turns that into a 401) rather than raising
here, so unauthenticated public routes (health) still pass through.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from config.config import settings


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach ``request_id`` and (when present) ``tenant_id`` to the request."""

    def __init__(self, app: ASGIApp) -> None:
        """Store the wrapped app."""
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        """Resolve context, then delegate."""
        request.state.request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.tenant_id = self._verify_tenant(request.headers.get("authorization"))
        response = await call_next(request)
        response.headers["x-request-id"] = request.state.request_id
        return response

    @staticmethod
    def _verify_tenant(auth_header: str | None) -> str | None:
        """Verify a ``Bearer <tenant>.<sig>`` token; return tenant or None."""
        if not auth_header or not auth_header.startswith("Bearer "):
            return None
        token = auth_header.removeprefix("Bearer ")
        tenant, _, sig = token.partition(".")
        if not tenant or not sig or not settings.auth_secret:
            return None
        expected = hmac.new(
            settings.auth_secret.encode(), tenant.encode(), hashlib.sha256
        ).hexdigest()
        return tenant if hmac.compare_digest(expected, sig) else None
