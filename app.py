"""
Minimal entrypoint that wires the HTTP Actions server and logging.
"""

from __future__ import annotations

import logging
import os
import sys

import uvicorn
from dotenv import load_dotenv

from config import get_settings
from logging_config import configure_logging
from server import create_starlette_app

load_dotenv()

# Track whether settings loaded successfully (Vault reachable)
_settings_degraded = False

try:
    settings = get_settings()
except Exception as e:
    # Vault unreachable or config error — fall back to env-only defaults
    # so the app can still start and serve /health.
    _settings_degraded = True
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger(__name__).error(
        "get_settings() failed (Vault unreachable?): %s — starting in degraded mode", e
    )
    from dataclasses import fields as _fields
    from config import Settings as _Settings

    # Build a minimal Settings from env vars only, using empty/default for secrets
    _defaults = {
        "app_version": os.getenv("APP_VERSION", "0.4.0"),
        "host": os.getenv("HOST", "0.0.0.0"),
        "port": int(os.getenv("PORT", "8000")),
        "log_file": os.getenv("LOG_FILE", "app.log"),
        "log_level": os.getenv("LOG_LEVEL", "WARNING").upper(),
        "default_timezone": os.getenv("DEFAULT_TIMEZONE", "America/Chicago"),
        "google_token_file": os.getenv("GOOGLE_TOKEN_FILE", "token.json"),
        "google_credentials_file": os.getenv("GOOGLE_CREDENTIALS_FILE"),
        "public_base_url": os.getenv("PUBLIC_BASE_URL", "http://localhost:8000"),
        "actions_name_for_human": os.getenv("ACTIONS_NAME_FOR_HUMAN", "Frank Bot"),
        "actions_name_for_model": os.getenv("ACTIONS_NAME_FOR_MODEL", "frank_bot"),
        "actions_description_for_human": os.getenv(
            "ACTIONS_DESCRIPTION_FOR_HUMAN",
            "Personal Google Calendar and Contacts assistant.",
        ),
        "actions_description_for_model": os.getenv(
            "ACTIONS_DESCRIPTION_FOR_MODEL",
            "Helps with listing Google Calendar events, creating new events, "
            "listing calendars, and searching Google Contacts.",
        ),
        "actions_openapi_path": os.getenv("ACTIONS_OPENAPI_PATH", "openapi/spec.json"),
        "swarm_api_version": os.getenv("SWARM_API_VERSION", "20240501"),
        "notify_numbers": (),
        "telegram_session_name": os.getenv("TELEGRAM_SESSION_NAME", "frank_bot"),
        "jorbs_db_path": os.getenv("JORBS_DB_PATH", "./data/jorbs.db"),
        "jorbs_progress_log": os.getenv("JORBS_PROGRESS_LOG", "./data/jorbs_progress.txt"),
        "agent_spend_limit": float(os.getenv("AGENT_SPEND_LIMIT", "100.0")),
        "context_reset_days": int(os.getenv("CONTEXT_RESET_DAYS", "3")),
        "debounce_telegram_seconds": int(os.getenv("DEBOUNCE_TELEGRAM_SECONDS", "3")),
        "debounce_sms_seconds": int(os.getenv("DEBOUNCE_SMS_SECONDS", "30")),
        "smtp_port": 587,
        "digest_time": "08:00",
        "android_device_serial": os.getenv("ANDROID_DEVICE_SERIAL", ""),
        # No default host: prefer USB; set ANDROID_ADB_HOST explicitly for TCP/IP ADB.
        "android_adb_host": os.getenv("ANDROID_ADB_HOST", ""),
        "android_adb_port": int(os.getenv("ANDROID_ADB_PORT", "5555")),
        "android_llm_model": os.getenv("ANDROID_LLM_MODEL", "gpt-5.2"),
        "android_maintenance_cron": os.getenv("ANDROID_MAINTENANCE_CRON", "0 3 1 * *"),
        "android_health_check_cron": os.getenv("ANDROID_HEALTH_CHECK_CRON", "0 4 * * 0"),
        "android_rate_limit_minute": int(os.getenv("ANDROID_RATE_LIMIT_MINUTE", "10")),
        "android_rate_limit_hour": int(os.getenv("ANDROID_RATE_LIMIT_HOUR", "100")),
        "google_calendar_scopes": ("https://www.googleapis.com/auth/calendar",),
        "google_contacts_scopes": ("https://www.googleapis.com/auth/contacts",),
    }
    # Fill None for all remaining Optional/secret fields
    for _f in _fields(_Settings):
        if _f.name not in _defaults:
            _defaults[_f.name] = None
    settings = _Settings(**_defaults)

configure_logging(settings.log_file, settings.log_level)

logger = logging.getLogger(__name__)
if _settings_degraded:
    logger.warning("Running in DEGRADED mode — secrets failed to load from Vault")
else:
    logger.info("Environment variables loaded")
logger.info("Logging to file: %s", settings.log_file)
logger.info("Log level: %s", settings.log_level)

# Export degraded flag so health endpoint can report it
settings_degraded = _settings_degraded
# Set to True if background loop fails to start (checked by /health)
background_loop_failed = False

starlette_app = create_starlette_app()


def main():
    """Main entry point used by Python or other process managers."""
    logger.info("Starting Actions server...")
    logger.info(
        "Server will listen on %s:%s",
        settings.host,
        settings.port,
    )
    logger.info(
        "✓ Health check: http://%s:%s/health",
        settings.host,
        settings.port,
    )
    logger.info("Press Ctrl-C to shutdown gracefully")

    try:
        uvicorn.run(
            starlette_app,
            host=settings.host,
            port=settings.port,
            log_config=None,
        )
    except KeyboardInterrupt:
        logger.info("Shutdown signal received - shutting down gracefully...")
    except Exception:
        logger.exception("Unexpected error while running uvicorn")
        raise
    finally:
        logger.info("Actions server stopped")
        for handler in logging.root.handlers[:]:
            handler.flush()
            handler.close()
            logging.root.removeHandler(handler)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nShutdown complete.", file=sys.stderr)
        sys.exit(0)
    except Exception:
        logger.exception("Fatal error")
        sys.exit(1)
    finally:
        logging.shutdown()
