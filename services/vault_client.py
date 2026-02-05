"""
Vault Client for Frank Bot

Fetches secrets from HashiCorp Vault using AppRole authentication.
Falls back to environment variables if Vault is unavailable.
Includes retry with exponential backoff for transient failures.

Pattern follows ~/dev/claudia/api/src/vault_client.py
"""

import logging
import os
import time
from typing import Any

import hvac


# Vault configuration from environment
VAULT_ADDR = os.environ.get("VAULT_ADDR", "")
VAULT_ROLE_ID = os.environ.get("VAULT_ROLE_ID", "")
VAULT_SECRET_ID = os.environ.get("VAULT_SECRET_ID", "")

# Retry configuration
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 10.0
BACKOFF_MULTIPLIER = 2.0

# Cache for Vault client and secrets
_vault_client: hvac.Client | None = None
_secret_cache: dict[str, dict[str, Any]] = {}

logger = logging.getLogger(__name__)


def vault_enabled() -> bool:
    """Check if Vault is configured."""
    return bool(VAULT_ADDR and VAULT_ROLE_ID and VAULT_SECRET_ID)


def _sleep_with_backoff(attempt: int) -> None:
    """Sleep with exponential backoff."""
    backoff = min(
        INITIAL_BACKOFF_SECONDS * (BACKOFF_MULTIPLIER ** attempt),
        MAX_BACKOFF_SECONDS
    )
    time.sleep(backoff)


def _get_vault_client(retry: bool = True) -> hvac.Client | None:
    """
    Get authenticated Vault client, or None if Vault is unavailable.

    Args:
        retry: If True, retry with backoff on transient failures.
    """
    global _vault_client

    if _vault_client is not None:
        # Check if still authenticated
        try:
            if _vault_client.is_authenticated():
                return _vault_client
        except Exception:
            pass
        # Token expired or connection lost, clear and re-authenticate
        _vault_client = None

    if not vault_enabled():
        logger.debug("Vault credentials not configured, skipping Vault")
        return None

    max_attempts = MAX_RETRIES if retry else 1
    last_error: Exception | None = None

    for attempt in range(max_attempts):
        try:
            client = hvac.Client(url=VAULT_ADDR)
            client.auth.approle.login(
                role_id=VAULT_ROLE_ID,
                secret_id=VAULT_SECRET_ID,
            )

            if client.is_authenticated():
                _vault_client = client
                if attempt > 0:
                    logger.info(f"Vault connection succeeded after {attempt + 1} attempts")
                return _vault_client
            else:
                logger.warning("Vault authentication failed: client not authenticated")
        except Exception as e:
            last_error = e
            if attempt < max_attempts - 1:
                logger.warning(
                    f"Vault connection attempt {attempt + 1} failed: {e}, retrying..."
                )
                _sleep_with_backoff(attempt)
            else:
                logger.error(f"Vault connection failed after {max_attempts} attempts: {e}")

    return None


def clear_client_cache() -> None:
    """Clear the Vault client cache, forcing re-authentication on next request."""
    global _vault_client
    _vault_client = None


def clear_secret_cache() -> None:
    """Clear the secret cache, forcing fresh fetches from Vault."""
    global _secret_cache
    _secret_cache = {}


def get_secret(path: str, retry: bool = True) -> dict[str, Any] | None:
    """
    Fetch a secret from Vault with retry and caching.

    Args:
        path: Secret path (e.g., "frank-bot/stytch")
        retry: If True, retry with backoff on transient failures.

    Returns:
        Secret data dict or None if unavailable
    """
    # Check cache first
    if path in _secret_cache:
        return _secret_cache[path]

    client = _get_vault_client(retry=retry)
    if client is None:
        return None

    max_attempts = MAX_RETRIES if retry else 1

    for attempt in range(max_attempts):
        try:
            response = client.secrets.kv.v2.read_secret_version(
                mount_point="secret",
                path=path,
            )
            secret_data = response["data"]["data"]
            # Cache the result
            _secret_cache[path] = secret_data
            return secret_data
        except hvac.exceptions.InvalidPath:
            # Secret doesn't exist - don't retry, just return None
            logger.warning(f"Secret not found at path: {path}")
            return None
        except Exception as e:
            if attempt < max_attempts - 1:
                logger.warning(
                    f"Vault read attempt {attempt + 1} for {path} failed: {e}, retrying..."
                )
                _sleep_with_backoff(attempt)
            else:
                logger.error(f"Vault read failed for {path} after {max_attempts} attempts: {e}")

    return None


def get_stytch_credentials() -> dict[str, str] | None:
    """
    Get Stytch credentials from Vault.

    Returns dict with:
        - project_id: Stytch project ID
        - secret: Stytch secret

    Returns None if Vault is unavailable.
    """
    return get_secret("frank-bot/stytch")


def get_telegram_credentials() -> dict[str, str] | None:
    """
    Get Telegram credentials from Vault.

    Returns dict with:
        - api_id: Telegram API ID
        - api_hash: Telegram API hash
        - phone: Phone number

    Returns None if Vault is unavailable.
    """
    return get_secret("frank-bot/telegram")


def get_telnyx_credentials() -> dict[str, str] | None:
    """
    Get Telnyx SMS credentials from Vault.

    Returns dict with:
        - api_key: Telnyx API key
        - phone_number: Telnyx phone number

    Returns None if Vault is unavailable.
    """
    return get_secret("frank-bot/telnyx")


def get_google_credentials() -> dict[str, str] | None:
    """
    Get Google OAuth credentials from Vault.

    Returns dict with:
        - client_id: Google client ID
        - client_secret: Google client secret

    Returns None if Vault is unavailable.
    """
    return get_secret("frank-bot/google")


def get_swarm_credentials() -> dict[str, str] | None:
    """
    Get Swarm/Foursquare credentials from Vault.

    Returns dict with:
        - oauth_token: Swarm OAuth token
        - api_key: Foursquare API key

    Returns None if Vault is unavailable.
    """
    return get_secret("frank-bot/swarm")


def get_telegram_bot_credentials() -> dict[str, str] | None:
    """
    Get Telegram Bot credentials from Vault.

    Returns dict with:
        - bot_token: Telegram bot token
        - chat_id: Default chat ID for notifications

    Returns None if Vault is unavailable.
    """
    return get_secret("frank-bot/telegram-bot")


def get_openai_credentials() -> dict[str, str] | None:
    """
    Get OpenAI API credentials from Vault.

    Returns dict with:
        - api_key: OpenAI API key

    Returns None if Vault is unavailable.
    """
    return get_secret("frank-bot/openai")


def get_claudia_credentials() -> dict[str, str] | None:
    """
    Get Claudia API credentials from Vault.

    Returns dict with:
        - api_url: Claudia API base URL
        - api_key: Claudia API key

    Returns None if Vault is unavailable.
    """
    return get_secret("frank-bot/claudia")


def get_android_credentials() -> dict[str, str] | None:
    """
    Get Android phone automation credentials from Vault.

    Returns dict with:
        - adb_host: IP address of the Android device
        - adb_port: ADB TCP port

    Returns None if Vault is unavailable.
    """
    return get_secret("frank-bot/android")


__all__ = [
    "vault_enabled",
    "get_secret",
    "get_stytch_credentials",
    "get_telegram_credentials",
    "get_telnyx_credentials",
    "get_google_credentials",
    "get_swarm_credentials",
    "get_telegram_bot_credentials",
    "get_openai_credentials",
    "get_claudia_credentials",
    "get_android_credentials",
    "clear_client_cache",
    "clear_secret_cache",
]
