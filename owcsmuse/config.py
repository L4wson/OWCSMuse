"""Environment-driven configuration (pydantic-settings).

Every setting can be supplied as an environment variable or in a `.env` file.
`FACEIT_API_KEY` is read verbatim; everything else uses the `OWCS_` prefix.
"""

from __future__ import annotations

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="OWCS_",
        extra="ignore",
    )

    # The FACEIT key intentionally has no prefix: the user supplies FACEIT_API_KEY.
    faceit_api_key: SecretStr = Field(
        validation_alias=AliasChoices("FACEIT_API_KEY", "OWCS_FACEIT_API_KEY"),
    )
    faceit_base_url: str = "https://open.faceit.com/data/v4"

    # Required, no default: an unset DATABASE_URL fails at startup rather than
    # silently connecting to some local database.
    database_url: str = Field(
        validation_alias=AliasChoices("DATABASE_URL", "OWCS_DATABASE_URL"),
    )
    # Schema the migrations create objects in and connections pin search_path to.
    db_schema: str = "public"
    migrations_dir: str = "migrations"

    # FACEIT list endpoints accept limit<=100 and reject offset>500 (offset must
    # also be a multiple of limit). 600 items is therefore the hard reach of a
    # single listing; the collector flags championships that hit it.
    page_size: int = Field(default=100, ge=1, le=100)
    max_offset: int = 500

    request_timeout: float = 30.0
    max_retries: int = 6
    backoff_base_seconds: float = 0.5
    backoff_cap_seconds: float = 60.0
    # Pause when the API reports this many (or fewer) requests remaining.
    rate_limit_headroom: int = 2
    # Fallback pacing when the API sends no rate-limit headers.
    default_rate_limit_per_second: float = 10.0

    log_level: str = "INFO"
    log_format: str = "json"  # "json" | "text"


def load_settings(**overrides) -> Settings:
    return Settings(**overrides)
