"""Test harness.

Tests run against a real, per-test Postgres (via pytest-postgresql) with
``alembic upgrade head`` applied inside it, so the balance-check trigger and the
deferred-constraint behavior are exercised for real — sqlite cannot express them,
so it is deliberately not an option (see DECISIONS.md → per-test-postgres). The
dummy env vars are set with ``setdefault`` BEFORE any engine import so test
configuration can never leak into a real dev run; do not reorder these imports.
"""

from __future__ import annotations

import os

os.environ.setdefault("LEDGER_ENV", "test")
os.environ.setdefault("LEDGER_AUTH_SECRET", "test-secret")

import pytest  # noqa: E402

# The DB-backed fixtures below require Postgres + `initdb` on PATH. The pure
# unit tests (money, matcher) do not use them and run anywhere.


@pytest.fixture
def auth_header() -> dict[str, str]:
    """A valid Bearer token for tenant 'acme' signed with the test secret."""
    import hashlib
    import hmac

    secret = os.environ["LEDGER_AUTH_SECRET"].encode()
    sig = hmac.new(secret, b"acme", hashlib.sha256).hexdigest()
    return {"Authorization": f"Bearer acme.{sig}"}
