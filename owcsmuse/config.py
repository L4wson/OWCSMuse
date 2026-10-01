"""Environment-driven configuration (pydantic-settings).

Every setting can be supplied as an environment variable or in a `.env` file.
`FACEIT_API_KEY` is read verbatim; everything else uses the `OWCS_` prefix.
`DATABASE_URL` is the only required setting; `FACEIT_API_KEY` is required only by ingest commands.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


# The repository root's .env, found from this file rather than the working directory, so
# `python -m owcsmuse ...` behaves the same wherever it is launched from. Real environment
# variables still win over it.
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        env_prefix="OWCS_",
        extra="ignore",
        populate_by_name=True,
    )

    # The FACEIT key intentionally has no prefix: the user supplies FACEIT_API_KEY. It is only
    # needed by commands that call FACEIT (discover, backfill, crawl, ...), never by serving
    # answers, so it is optional here and demanded by `require_faceit_key()` at the point of use.
    faceit_api_key: Optional[SecretStr] = Field(
        default=None,
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

    # Liquipedia (LiquipediaDB API v3). No request is ever made unless OWCS_LIQUIPEDIA_ENABLED is also set in the
    # environment (see liquipedia/client.py); the key alone is not consent to spend the hourly budget.
    liquipedia_api_key: Optional[SecretStr] = Field(
        default=None,
        validation_alias=AliasChoices("LIQUIPEDIA_API_KEY", "OWCS_LIQUIPEDIA_API_KEY"),
    )
    liquipedia_base_url: str = "https://api.liquipedia.net/api/v3"
    liquipedia_wiki: str = "overwatch"
    liquipedia_hourly_budget: int = Field(default=60, ge=1)   # the approved allowance: 60 requests per hour
    liquipedia_page_limit: int = Field(default=500, ge=1, le=1000)   # rows per request
    liquipedia_min_interval: float = Field(default=2.0, ge=0)        # seconds between requests

    log_level: str = "INFO"
    log_format: str = "json"  # "json" | "text"

    def require_faceit_key(self) -> str:
        """The FACEIT key, or a clear failure for a command that cannot run without it."""
        if self.faceit_api_key is None or not self.faceit_api_key.get_secret_value().strip():
            raise RuntimeError(
                "FACEIT_API_KEY is required for commands that call FACEIT; set it in the environment or .env"
            )
        return self.faceit_api_key.get_secret_value()


def load_settings(**overrides) -> Settings:
    return Settings(**overrides)
