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


@dataclass(frozen=True)
class Settings:
    """Centralized configuration values."""

    app_version: str
    host: str
    port: int
    log_file: str
    log_level: str
    default_timezone: str
    google_token_file: str
    google_credentials_file: str | None
    google_calendar_scopes: tuple[str, ...]
    google_contacts_scopes: tuple[str, ...]
    public_base_url: str
    actions_api_key: str | None
    actions_name_for_human: str
    actions_name_for_model: str
    actions_description_for_human: str
    actions_description_for_model: str
    actions_logo_url: str | None
    actions_contact_email: str | None
    actions_legal_url: str | None
    actions_openapi_path: str
    swarm_oauth_token: str | None
    swarm_api_version: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings derived from the environment."""
    base_url = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
    return Settings(
        app_version=os.getenv("APP_VERSION", "0.3.0"),
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        log_file=os.getenv("LOG_FILE", "app.log"),
        log_level=os.getenv("LOG_LEVEL", "DEBUG").upper(),
        default_timezone=os.getenv("DEFAULT_TIMEZONE", "America/Chicago"),
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
        public_base_url=base_url,
        actions_api_key=os.getenv("ACTIONS_API_KEY"),
        actions_name_for_human=os.getenv(
            "ACTIONS_NAME_FOR_HUMAN",
            "Frank Bot",
        ),
        actions_name_for_model=os.getenv(
            "ACTIONS_NAME_FOR_MODEL",
            "frank_bot",
        ),
        actions_description_for_human=os.getenv(
            "ACTIONS_DESCRIPTION_FOR_HUMAN",
            "Personal Google Calendar and Contacts assistant.",
        ),
        actions_description_for_model=os.getenv(
            "ACTIONS_DESCRIPTION_FOR_MODEL",
            (
                "Helps with listing Google Calendar events, creating new "
                "events, listing calendars, and searching Google Contacts."
            ),
        ),
        actions_logo_url=os.getenv("ACTIONS_LOGO_URL"),
        actions_contact_email=os.getenv("ACTIONS_CONTACT_EMAIL"),
        actions_legal_url=os.getenv("ACTIONS_LEGAL_URL"),
        actions_openapi_path=os.getenv(
            "ACTIONS_OPENAPI_PATH",
            "actions/openapi.json",
        ),
        swarm_oauth_token=os.getenv("SWARM_OAUTH_TOKEN"),
        swarm_api_version=os.getenv("SWARM_API_VERSION", "20240501"),
    )
