"""
Application settings helpers.

Loads secrets from Vault with environment variable fallback.

On startup, if Vault is configured but unreachable (e.g. concordia-vault
hasn't finished starting after a reboot), we retry with exponential backoff
before falling through to env-var fallback. This prevents the race condition
where frank_bot starts before Vault is ready and permanently caches empty
secrets via @lru_cache.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from functools import lru_cache

from services.vault_client import (
    vault_enabled,
    get_claudia_credentials,
    get_earshot_credentials,
    get_email_credentials,
    get_google_credentials,
    get_openai_credentials,
    get_stytch_credentials,
    get_swarm_credentials,
    get_telegram_credentials,
    get_telegram_bot_credentials,
    get_telnyx_credentials,
    clear_client_cache,
    clear_secret_cache,
)

logger = logging.getLogger(__name__)

VAULT_STARTUP_MAX_ATTEMPTS = int(os.environ.get("VAULT_STARTUP_MAX_ATTEMPTS", "8"))
VAULT_STARTUP_INITIAL_BACKOFF = float(os.environ.get("VAULT_STARTUP_INITIAL_BACKOFF", "2.0"))
VAULT_STARTUP_MAX_BACKOFF = float(os.environ.get("VAULT_STARTUP_MAX_BACKOFF", "30.0"))
VAULT_STARTUP_BACKOFF_MULTIPLIER = float(os.environ.get("VAULT_STARTUP_BACKOFF_MULTIPLIER", "2.0"))


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
    owner_name: str
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
    # Earshot integration settings
    earshot_api_url: str | None
    earshot_api_key: str | None
    # Android phone settings
    android_device_serial: str
    android_adb_host: str
    android_adb_port: int
    android_llm_model: str
    android_llm_api_key: str | None
    android_maintenance_cron: str
    android_health_check_cron: str
    # Android phone rate limiting
    android_rate_limit_minute: int
    android_rate_limit_hour: int


def _empty_secrets() -> dict[str, str | None]:
    """Return a dict of all secret keys initialized to None."""
    return {
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
        "smtp_host": None,
        "smtp_port": None,
        "smtp_user": None,
        "smtp_password": None,
        "digest_email_to": None,
        "digest_time": None,
        "earshot_api_url": None,
        "earshot_api_key": None,
        "android_device_serial": None,
        "android_adb_host": None,
        "android_adb_port": None,
        "android_llm_api_key": None,
        "actions_api_key": None,
    }


def _fetch_vault_secrets(secrets: dict[str, str | None]) -> bool:
    """
    Populate *secrets* dict from Vault. Returns True if Vault was reachable
    and at least one credential path resolved (i.e. the connection worked).
    """
    from services.vault_client import get_android_credentials, get_actions_credentials

    google_creds = get_google_credentials()
    if google_creds:
        secrets["google_client_id"] = google_creds.get("client_id")
        secrets["google_client_secret"] = google_creds.get("client_secret")

    stytch_creds = get_stytch_credentials()
    if stytch_creds:
        secrets["stytch_project_id"] = stytch_creds.get("project_id")
        secrets["stytch_secret"] = stytch_creds.get("secret")

    swarm_creds = get_swarm_credentials()
    if swarm_creds:
        secrets["swarm_oauth_token"] = swarm_creds.get("oauth_token")
        secrets["foursquare_api_key"] = (
            swarm_creds.get("api_key")
            or swarm_creds.get("foursquare_key")
        )

    telegram_creds = get_telegram_credentials()
    if telegram_creds:
        secrets["telegram_api_id"] = telegram_creds.get("api_id")
        secrets["telegram_api_hash"] = telegram_creds.get("api_hash")
        secrets["telegram_phone"] = telegram_creds.get("phone")

    telegram_bot_creds = get_telegram_bot_credentials()
    if telegram_bot_creds:
        secrets["telegram_bot_token"] = telegram_bot_creds.get("token")
        secrets["telegram_bot_chat_id"] = telegram_bot_creds.get("chat_id")

    telnyx_creds = get_telnyx_credentials()
    if telnyx_creds:
        secrets["telnyx_api_key"] = telnyx_creds.get("api_key")
        secrets["telnyx_phone_number"] = telnyx_creds.get("phone_number")

    openai_creds = get_openai_credentials()
    if openai_creds:
        secrets["openai_api_key"] = openai_creds.get("api_key")

    email_creds = get_email_credentials()
    if email_creds:
        secrets["smtp_host"] = email_creds.get("smtp_host")
        smtp_port = email_creds.get("smtp_port")
        if smtp_port is not None:
            secrets["smtp_port"] = str(smtp_port)
        secrets["smtp_user"] = email_creds.get("smtp_user")
        secrets["smtp_password"] = email_creds.get("smtp_password")
        secrets["digest_email_to"] = email_creds.get("digest_email_to")
        secrets["digest_time"] = email_creds.get("digest_time")

    claudia_creds = get_claudia_credentials()
    if claudia_creds:
        secrets["claudia_api_url"] = claudia_creds.get("api_url")
        secrets["claudia_api_key"] = claudia_creds.get("api_key")

    earshot_creds = get_earshot_credentials()
    if earshot_creds:
        secrets["earshot_api_url"] = earshot_creds.get("api_url")
        secrets["earshot_api_key"] = earshot_creds.get("api_key")

    android_creds = get_android_credentials()
    if android_creds:
        secrets["android_device_serial"] = android_creds.get("device_serial")
        secrets["android_adb_host"] = android_creds.get("adb_host")
        secrets["android_adb_port"] = android_creds.get("adb_port")
        secrets["android_llm_api_key"] = android_creds.get("llm_api_key")

    actions_creds = get_actions_credentials()
    if actions_creds:
        secrets["actions_api_key"] = actions_creds.get("api_key")

    # Consider Vault "reachable" if we got at least one non-None credential.
    # (frank-bot/email is known to be missing, so we don't count on it.)
    got_something = any(v is not None for v in secrets.values())
    return got_something


def _load_secrets() -> dict[str, str | None]:
    """
    Load secrets from Vault with environment variable fallback.

    When Vault is configured but unreachable (e.g. concordia-vault hasn't
    started yet after a reboot), retries with exponential backoff before
    falling through to env-var defaults. This prevents the startup race
    condition where get_settings()'s @lru_cache permanently locks in empty
    secrets.

    Returns a dict with all secret values.
    """
    vault_is_enabled = vault_enabled()
    allow_env_secret_fallback = (
        os.getenv("ALLOW_ENV_SECRET_FALLBACK", "false").lower() == "true"
    )

    secrets = _empty_secrets()

    if vault_is_enabled:
        logger.info("Loading secrets from Vault")
        vault_ok = False
        backoff = VAULT_STARTUP_INITIAL_BACKOFF

        for attempt in range(VAULT_STARTUP_MAX_ATTEMPTS):
            # Reset caches so each attempt talks to Vault fresh
            if attempt > 0:
                clear_client_cache()
                clear_secret_cache()
                secrets = _empty_secrets()

            try:
                vault_ok = _fetch_vault_secrets(secrets)
            except Exception as exc:
                logger.warning(
                    "Vault secret fetch attempt %d/%d failed: %s",
                    attempt + 1, VAULT_STARTUP_MAX_ATTEMPTS, exc,
                )
                vault_ok = False

            if vault_ok:
                if attempt > 0:
                    logger.info(
                        "Vault secrets loaded successfully after %d attempt(s)",
                        attempt + 1,
                    )
                break

            # Vault was unreachable -- wait before retrying
            import services.vault_client as _vc
            if getattr(_vc, "_vault_connection_failed", False):
                if attempt < VAULT_STARTUP_MAX_ATTEMPTS - 1:
                    logger.warning(
                        "Vault unreachable on attempt %d/%d, retrying in %.1fs...",
                        attempt + 1, VAULT_STARTUP_MAX_ATTEMPTS, backoff,
                    )
                    time.sleep(backoff)
                    backoff = min(backoff * VAULT_STARTUP_BACKOFF_MULTIPLIER,
                                  VAULT_STARTUP_MAX_BACKOFF)
                    # Reset the connection-failed flag so vault_client retries
                    _vc._vault_connection_failed = False
                else:
                    logger.error(
                        "Vault still unreachable after %d attempts — "
                        "proceeding with env-var fallback",
                        VAULT_STARTUP_MAX_ATTEMPTS,
                    )
            else:
                # Vault was reachable but returned no secrets -- don't retry
                break
    else:
        logger.info("Vault not configured, using environment variables")

    # Env secret fallback:
    # - Allowed when Vault is NOT configured (local/dev)
    # - Allowed when Vault connection failed (graceful degradation)
    # - Optionally allowed with Vault via ALLOW_ENV_SECRET_FALLBACK=true
    import services.vault_client as _vc
    vault_conn_failed = getattr(_vc, "_vault_connection_failed", False)
    if vault_conn_failed:
        logger.warning(
            "Vault connection failed — falling back to environment variables for secrets"
        )
    if (not vault_is_enabled) or allow_env_secret_fallback or vault_conn_failed:
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
        if not secrets["smtp_host"]:
            secrets["smtp_host"] = os.getenv("SMTP_HOST")
        if not secrets["smtp_port"]:
            secrets["smtp_port"] = os.getenv("SMTP_PORT")
        if not secrets["smtp_user"]:
            secrets["smtp_user"] = os.getenv("SMTP_USER")
        if not secrets["smtp_password"]:
            secrets["smtp_password"] = os.getenv("SMTP_PASSWORD")
        if not secrets["digest_email_to"]:
            secrets["digest_email_to"] = os.getenv("DIGEST_EMAIL_TO")
        if not secrets["digest_time"]:
            secrets["digest_time"] = os.getenv("DIGEST_TIME")
        if not secrets["earshot_api_url"]:
            secrets["earshot_api_url"] = os.getenv("EARSHOT_API_URL")
        if not secrets["earshot_api_key"]:
            secrets["earshot_api_key"] = os.getenv("EARSHOT_API_KEY")
        if not secrets["android_llm_api_key"]:
            secrets["android_llm_api_key"] = os.getenv("ANDROID_LLM_API_KEY")
        if not secrets["android_device_serial"]:
            secrets["android_device_serial"] = os.getenv(
                "ANDROID_DEVICE_SERIAL", ""
            )
        if not secrets["android_adb_host"]:
            secrets["android_adb_host"] = os.getenv(
                "ANDROID_ADB_HOST", ""
            )
        if not secrets["android_adb_port"]:
            secrets["android_adb_port"] = os.getenv(
                "ANDROID_ADB_PORT", "5555"
            )
        if not secrets["actions_api_key"]:
            secrets["actions_api_key"] = os.getenv("ACTIONS_API_KEY")
    else:
        # Vault is configured and env secret fallback is disabled.
        # If any secret env vars are present, log a warning (they will be ignored).
        secret_env_vars = [
            "GOOGLE_CLIENT_ID",
            "GOOGLE_CLIENT_SECRET",
            "STYTCH_PROJECT_ID",
            "STYTCH_SECRET",
            "SWARM_OAUTH_TOKEN",
            "FOURSQUARE_API_KEY",
            "TELEGRAM_API_ID",
            "TELEGRAM_API_HASH",
            "TELEGRAM_PHONE",
            "TELEGRAM_BOT_TOKEN",
            "TELEGRAM_BOT_CHAT_ID",
            "TELNYX_LET_FOOD_INTO_CIVIC_KEY",
            "TELNYX_PHONE_NUMBER",
            "OPENAI_API_KEY",
            "CLAUDIA_API_URL",
            "CLAUDIA_API_KEY",
            "SMTP_HOST",
            "SMTP_PORT",
            "SMTP_USER",
            "SMTP_PASSWORD",
            "DIGEST_EMAIL_TO",
            "DIGEST_TIME",
            "EARSHOT_API_URL",
            "EARSHOT_API_KEY",
            "ANDROID_LLM_API_KEY",
            "ANDROID_DEVICE_SERIAL",
            "ANDROID_ADB_HOST",
            "ANDROID_ADB_PORT",
            "ACTIONS_API_KEY",
        ]
        present = [k for k in secret_env_vars if os.getenv(k)]
        if present:
            logger.warning(
                "Vault is configured; ignoring secret env vars: %s",
                ", ".join(present),
            )

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

    smtp_port_raw = secrets.get("smtp_port") or "587"
    try:
        smtp_port = int(str(smtp_port_raw))
    except (ValueError, TypeError):
        smtp_port = 587

    digest_time = (secrets.get("digest_time") or "08:00").strip() or "08:00"

    return Settings(
        app_version=os.getenv("APP_VERSION", "0.4.0"),
        owner_name=os.getenv("OWNER_NAME", "Sean Reardon"),
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
        actions_api_key=secrets["actions_api_key"],
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
        jorbs_db_path=os.getenv("JORBS_DB_PATH", "./data/jorbs"),
        jorbs_progress_log=os.getenv("JORBS_PROGRESS_LOG", "./data/jorbs_progress.txt"),
        agent_spend_limit=float(os.getenv("AGENT_SPEND_LIMIT", "100.0")),
        context_reset_days=int(os.getenv("CONTEXT_RESET_DAYS", "3")),
        debounce_telegram_seconds=int(os.getenv("DEBOUNCE_TELEGRAM_SECONDS", "3")),
        debounce_sms_seconds=int(os.getenv("DEBOUNCE_SMS_SECONDS", "30")),
        # Email/SMTP settings for jorb notifications
        smtp_host=secrets.get("smtp_host"),
        smtp_port=smtp_port,
        smtp_user=secrets.get("smtp_user"),
        smtp_password=secrets.get("smtp_password"),
        digest_email_to=secrets.get("digest_email_to"),
        digest_time=digest_time,
        # Claudia integration
        claudia_api_url=secrets["claudia_api_url"],
        claudia_api_key=secrets["claudia_api_key"],
        # Earshot integration
        earshot_api_url=secrets["earshot_api_url"],
        earshot_api_key=secrets["earshot_api_key"],
        # Android phone settings
        android_device_serial=secrets["android_device_serial"] or "",
        # Keep TCP/IP ADB usable even when Vault has no adb_host configured.
        android_adb_host=(
            (secrets.get("android_adb_host") or "").strip()
            or os.getenv("ANDROID_ADB_HOST", "10.0.0.95").strip()
        ),
        android_adb_port=int(secrets["android_adb_port"] or "5555"),
        android_llm_model=os.getenv("ANDROID_LLM_MODEL", "gpt-5.2"),
        android_llm_api_key=secrets.get("android_llm_api_key"),
        android_maintenance_cron=os.getenv("ANDROID_MAINTENANCE_CRON", "0 3 1 * *"),
        android_health_check_cron=os.getenv("ANDROID_HEALTH_CHECK_CRON", "0 4 * * 0"),
        android_rate_limit_minute=int(os.getenv("ANDROID_RATE_LIMIT_MINUTE", "10")),
        android_rate_limit_hour=int(os.getenv("ANDROID_RATE_LIMIT_HOUR", "100")),
    )

