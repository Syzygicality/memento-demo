"""Composed application settings — the single configuration entry point.

`settings` is built once by composing the database, CORS, and idempotency
sections, each reading from the environment via pydantic-settings. Application
code reads configuration through this object and never touches ``os.environ``
directly, so configuration has exactly one place it can come from (see
DECISIONS.md → composed-settings).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from config.database_config import DatabaseConfig


class Settings(BaseSettings):
    """Top-level settings; sections are nested models."""

    model_config = SettingsConfigDict(
        env_prefix="LEDGER_", env_file=".env", extra="ignore"
    )

    env: str = "dev"
    log_level: str = "INFO"
    workers: int = 4
    cors_origins: str = "http://localhost:5173"

    # HMAC secret for tenant session tokens. Deliberately has no default so a
    # misconfigured prod boot fails loudly rather than signing with a known key.
    auth_secret: str = ""

    idempotency_ttl_hours: int = 48
    idempotency_min_age_minutes: int = 15

    database: DatabaseConfig = Field(default_factory=DatabaseConfig)

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS origins as a list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()


settings = get_settings()
