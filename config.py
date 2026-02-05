"""
Application settings helpers.

Loads secrets from Vault with environment variable fallback.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache

from services.vault_client import (
    vault_enabled,
    get_claudia_credentials,
    get_google_credentials,
    get_openai_credentials,
    get_stytch_credentials,
    get_swarm_credentials,
    get_telegram_credentials,
    get_telegram_bot_credentials,
    get_telnyx_credentials,
)

logger = logging.getLogger(__name__)


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
    google_client_id: str | None
    google_client_secret: str | None
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
    telnyx_api_key: str | None
    telnyx_phone_number: str | None
    notify_numbers: tuple[str, ...]
    telegram_api_id: int | None
    telegram_api_hash: str | None
    telegram_phone: str | None
    telegram_session_name: str
    telegram_bot_token: str | None
    telegram_bot_chat_id: str | None
    stytch_project_id: str | None
    stytch_secret: str | None
    # Jorb system settings
    openai_api_key: str | None
    jorbs_db_path: str
    jorbs_progress_log: str
    agent_spend_limit: float
    context_reset_days: int
    debounce_telegram_seconds: int
    debounce_sms_seconds: int
    # Email/SMTP settings for jorb notifications
    smtp_host: str | None
    smtp_port: int
    smtp_user: str | None
    smtp_password: str | None
    digest_email_to: str | None
    digest_time: str
    # Claudia integration settings
    claudia_api_url: str | None
    claudia_api_key: str | None
    # Android phone settings
    android_adb_host: str
    android_adb_port: int
    android_llm_model: str
    android_llm_api_key: str | None
    android_maintenance_cron: str
    android_health_check_cron: str
    # Android phone rate limiting
    android_rate_limit_minute: int
    android_rate_limit_hour: int


def _load_secrets() -> dict[str, str | None]:
    """
    Load secrets from Vault with environment variable fallback.

    Returns a dict with all secret values.
    """
    secrets: dict[str, str | None] = {
        "google_client_id": None,
        "google_client_secret": None,
        "stytch_project_id": None,
        "stytch_secret": None,
        "swarm_oauth_token": None,
        "foursquare_api_key": None,
        "telegram_api_id": None,
        "telegram_api_hash": None,
        "telegram_phone": None,
        "telegram_bot_token": None,
        "telegram_bot_chat_id": None,
        "telnyx_api_key": None,
        "telnyx_phone_number": None,
        "openai_api_key": None,
        "claudia_api_url": None,
        "claudia_api_key": None,
    }

    if vault_enabled():
        logger.info("Loading secrets from Vault")

        # Google credentials
        google_creds = get_google_credentials()
        if google_creds:
            secrets["google_client_id"] = google_creds.get("client_id")
            secrets["google_client_secret"] = google_creds.get("client_secret")

        # Stytch credentials
        stytch_creds = get_stytch_credentials()
        if stytch_creds:
            secrets["stytch_project_id"] = stytch_creds.get("project_id")
            secrets["stytch_secret"] = stytch_creds.get("secret")

        # Swarm credentials
        swarm_creds = get_swarm_credentials()
        if swarm_creds:
            secrets["swarm_oauth_token"] = swarm_creds.get("oauth_token")
            secrets["foursquare_api_key"] = swarm_creds.get("api_key")

        # Telegram credentials
        telegram_creds = get_telegram_credentials()
        if telegram_creds:
            secrets["telegram_api_id"] = telegram_creds.get("api_id")
            secrets["telegram_api_hash"] = telegram_creds.get("api_hash")
            secrets["telegram_phone"] = telegram_creds.get("phone")

        # Telegram Bot credentials
        telegram_bot_creds = get_telegram_bot_credentials()
        if telegram_bot_creds:
            secrets["telegram_bot_token"] = telegram_bot_creds.get("token")
            secrets["telegram_bot_chat_id"] = telegram_bot_creds.get("chat_id")

        # Telnyx credentials
        telnyx_creds = get_telnyx_credentials()
        if telnyx_creds:
            secrets["telnyx_api_key"] = telnyx_creds.get("api_key")
            secrets["telnyx_phone_number"] = telnyx_creds.get("phone_number")

        # OpenAI credentials
        openai_creds = get_openai_credentials()
        if openai_creds:
            secrets["openai_api_key"] = openai_creds.get("api_key")

        # Claudia credentials
        claudia_creds = get_claudia_credentials()
        if claudia_creds:
            secrets["claudia_api_url"] = claudia_creds.get("api_url")
            secrets["claudia_api_key"] = claudia_creds.get("api_key")
    else:
        logger.info("Vault not configured, using environment variables")

    # Fallback to environment variables for any missing values
    if not secrets["google_client_id"]:
        secrets["google_client_id"] = os.getenv("GOOGLE_CLIENT_ID")
    if not secrets["google_client_secret"]:
        secrets["google_client_secret"] = os.getenv("GOOGLE_CLIENT_SECRET")
    if not secrets["stytch_project_id"]:
        secrets["stytch_project_id"] = os.getenv("STYTCH_PROJECT_ID")
    if not secrets["stytch_secret"]:
        secrets["stytch_secret"] = os.getenv("STYTCH_SECRET")
    if not secrets["swarm_oauth_token"]:
        secrets["swarm_oauth_token"] = os.getenv("SWARM_OAUTH_TOKEN")
    if not secrets["foursquare_api_key"]:
        secrets["foursquare_api_key"] = os.getenv("FOURSQUARE_API_KEY")
    if not secrets["telegram_api_id"]:
        secrets["telegram_api_id"] = os.getenv("TELEGRAM_API_ID")
    if not secrets["telegram_api_hash"]:
        secrets["telegram_api_hash"] = os.getenv("TELEGRAM_API_HASH")
    if not secrets["telegram_phone"]:
        secrets["telegram_phone"] = os.getenv("TELEGRAM_PHONE")
    if not secrets["telegram_bot_token"]:
        secrets["telegram_bot_token"] = os.getenv("TELEGRAM_BOT_TOKEN")
    if not secrets["telegram_bot_chat_id"]:
        secrets["telegram_bot_chat_id"] = os.getenv("TELEGRAM_BOT_CHAT_ID")
    if not secrets["telnyx_api_key"]:
        secrets["telnyx_api_key"] = os.getenv("TELNYX_LET_FOOD_INTO_CIVIC_KEY")
    if not secrets["telnyx_phone_number"]:
        secrets["telnyx_phone_number"] = os.getenv("TELNYX_PHONE_NUMBER")
    if not secrets["openai_api_key"]:
        secrets["openai_api_key"] = os.getenv("OPENAI_API_KEY")
    if not secrets["claudia_api_url"]:
        secrets["claudia_api_url"] = os.getenv("CLAUDIA_API_URL")
    if not secrets["claudia_api_key"]:
        secrets["claudia_api_key"] = os.getenv("CLAUDIA_API_KEY")

    return secrets


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings derived from Vault/environment."""
    base_url = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")

    # Load secrets from Vault with env var fallback
    secrets = _load_secrets()

    # Parse telegram_api_id as int
    telegram_api_id = None
    if secrets["telegram_api_id"]:
        try:
            telegram_api_id = int(secrets["telegram_api_id"])
        except (ValueError, TypeError):
            pass

    return Settings(
        app_version=os.getenv("APP_VERSION", "0.4.0"),
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        log_file=os.getenv("LOG_FILE", "app.log"),
        log_level=os.getenv("LOG_LEVEL", "DEBUG").upper(),
        default_timezone=os.getenv("DEFAULT_TIMEZONE", "America/Chicago"),
        google_token_file=os.getenv("GOOGLE_TOKEN_FILE", "token.json"),
        google_credentials_file=os.getenv("GOOGLE_CREDENTIALS_FILE"),
        google_client_id=secrets["google_client_id"],
        google_client_secret=secrets["google_client_secret"],
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
            "openapi/spec.json",
        ),
        swarm_oauth_token=secrets["swarm_oauth_token"],
        swarm_api_version=os.getenv("SWARM_API_VERSION", "20240501"),
        telnyx_api_key=secrets["telnyx_api_key"],
        telnyx_phone_number=secrets["telnyx_phone_number"],
        notify_numbers=_parse_scopes("NOTIFY_NUMBERS", ()),
        telegram_api_id=telegram_api_id,
        telegram_api_hash=secrets["telegram_api_hash"],
        telegram_phone=secrets["telegram_phone"],
        telegram_session_name=os.getenv("TELEGRAM_SESSION_NAME", "frank_bot"),
        telegram_bot_token=secrets["telegram_bot_token"],
        telegram_bot_chat_id=secrets["telegram_bot_chat_id"],
        stytch_project_id=secrets["stytch_project_id"],
        stytch_secret=secrets["stytch_secret"],
        # Jorb system settings
        openai_api_key=secrets["openai_api_key"],
        jorbs_db_path=os.getenv("JORBS_DB_PATH", "./data/jorbs.db"),
        jorbs_progress_log=os.getenv("JORBS_PROGRESS_LOG", "./data/jorbs_progress.txt"),
        agent_spend_limit=float(os.getenv("AGENT_SPEND_LIMIT", "100.0")),
        context_reset_days=int(os.getenv("CONTEXT_RESET_DAYS", "3")),
        debounce_telegram_seconds=int(os.getenv("DEBOUNCE_TELEGRAM_SECONDS", "60")),
        debounce_sms_seconds=int(os.getenv("DEBOUNCE_SMS_SECONDS", "30")),
        # Email/SMTP settings for jorb notifications
        smtp_host=os.getenv("SMTP_HOST"),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        smtp_user=os.getenv("SMTP_USER"),
        smtp_password=os.getenv("SMTP_PASSWORD"),
        digest_email_to=os.getenv("DIGEST_EMAIL_TO"),
        digest_time=os.getenv("DIGEST_TIME", "08:00"),
        # Claudia integration
        claudia_api_url=secrets["claudia_api_url"],
        claudia_api_key=secrets["claudia_api_key"],
        # Android phone settings
        android_adb_host=os.getenv("ANDROID_ADB_HOST", "10.0.0.95"),
        android_adb_port=int(os.getenv("ANDROID_ADB_PORT", "5555")),
        android_llm_model=os.getenv("ANDROID_LLM_MODEL", "gpt-4o"),
        android_llm_api_key=os.getenv("ANDROID_LLM_API_KEY"),
        android_maintenance_cron=os.getenv("ANDROID_MAINTENANCE_CRON", "0 3 1 * *"),
        android_health_check_cron=os.getenv("ANDROID_HEALTH_CHECK_CRON", "0 4 * * 0"),
        android_rate_limit_minute=int(os.getenv("ANDROID_RATE_LIMIT_MINUTE", "10")),
        android_rate_limit_hour=int(os.getenv("ANDROID_RATE_LIMIT_HOUR", "100")),
    )

