"""
Application settings helpers.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _parse_scopes(env_name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    """Split comma-separated scope values from the environment."""
    raw = os.getenv(env_name, "")
    if not raw:
        return default
    scopes = tuple(
        scope.strip()
        for scope in raw.split(",")
        if scope.strip()
    )
    return scopes or default


def _parse_bool(env_name: str, default: bool) -> bool:
    """Return boolean from environment string values."""
    raw = os.getenv(env_name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Centralized configuration values."""

    host: str
    port: int
    log_file: str
    log_level: str
    mcp_endpoint: str
    default_timezone: str
    google_token_file: str
    google_credentials_file: str | None
    google_calendar_scopes: tuple[str, ...]
    google_contacts_scopes: tuple[str, ...]
    streamable_stateless: bool
    streamable_json_response: bool


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings derived from the environment."""
    return Settings(
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        log_file=os.getenv("LOG_FILE", "app.log"),
        log_level=os.getenv("LOG_LEVEL", "DEBUG").upper(),
        mcp_endpoint=os.getenv("MCP_ENDPOINT", os.getenv("SSE_ENDPOINT", "/mcp")),
        default_timezone=os.getenv("DEFAULT_TIMEZONE", "UTC"),
        google_token_file=os.getenv("GOOGLE_TOKEN_FILE", "token.json"),
        google_credentials_file=os.getenv("GOOGLE_CREDENTIALS_FILE"),
        google_calendar_scopes=_parse_scopes(
            "GOOGLE_CALENDAR_SCOPES",
            ("https://www.googleapis.com/auth/calendar",),
        ),
        google_contacts_scopes=_parse_scopes(
            "GOOGLE_CONTACTS_SCOPES",
            ("https://www.googleapis.com/auth/contacts",),
        ),
        streamable_stateless=_parse_bool("MCP_STREAMABLE_STATELESS", False),
        streamable_json_response=_parse_bool("MCP_STREAMABLE_JSON_RESPONSE", False),
    )

