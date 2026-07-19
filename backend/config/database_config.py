"""Database configuration section.

Reads env vars via pydantic-settings and exposes a single async DSN. The full
``LEDGER_DATABASE_URL`` wins when provided; otherwise the DSN is assembled from
the individual parts so a local `.env` can omit the URL and still work.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseConfig(BaseSettings):
    """Postgres connection settings (prefix ``LEDGER_DATABASE_``)."""

    model_config = SettingsConfigDict(env_prefix="LEDGER_DATABASE_", extra="ignore")

    url: str | None = None
    host: str = "localhost"
    port: int = 5432
    name: str = "ledger"
    user: str = "ledger"
    password: str = "ledger"

    # Pool sizing is conservative: money endpoints are short and hold row locks,
    # so a fat pool would only deepen lock contention (see DECISIONS.md).
    pool_size: int = Field(default=10)
    max_overflow: int = Field(default=5)

    @property
    def dsn(self) -> str:
        """Return the async SQLAlchemy DSN."""
        if self.url:
            return self.url
        return (
            f"postgresql+asyncpg://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.name}"
        )
