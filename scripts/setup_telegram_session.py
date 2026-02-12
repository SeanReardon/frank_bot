#!/usr/bin/env python
"""
Interactive Telegram session setup for Frank Bot.

This script authenticates your Telegram account using Telethon and creates
a session file that allows Frank Bot to send and receive messages on your
behalf.

Usage:
    poetry run python scripts/setup_telegram_session.py

Requirements:
    Prefer storing Telegram credentials in Concordia Vault at
    `secret/frank-bot/telegram` (managed by `terraform/vault/`).

    For one-off local setup, you can also provide (or be prompted for):
    - TELEGRAM_API_ID
    - TELEGRAM_API_HASH
    - TELEGRAM_PHONE
    - TELEGRAM_SESSION_NAME (optional, default: frank_bot)

The script will:
1. Connect to Telegram using your API credentials
2. Send a verification code to your Telegram app (or SMS as fallback)
3. Prompt you to enter the code
4. If 2FA is enabled, prompt for your password
5. Create a .session file for persistent authentication
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Add project root to path for imports
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def get_env_or_prompt(var_name: str, prompt_text: str, is_secret: bool = False) -> str:
    """Get value from environment or prompt user."""
    value = os.getenv(var_name, "").strip()
    if value:
        return value

    if is_secret:
        import getpass
        return getpass.getpass(prompt_text).strip()
    else:
        return input(prompt_text).strip()


async def setup_session() -> None:
    """Run the interactive Telegram session setup."""
    from telethon import TelegramClient
    from telethon.errors import (
        FloodWaitError,
        PhoneCodeExpiredError,
        PhoneCodeInvalidError,
        SessionPasswordNeededError,
    )

    print("=" * 60)
    print("Frank Bot - Telegram Session Setup")
    print("=" * 60)
    print()
    print("This script will authenticate your Telegram account and create")
    print("a session file for Frank Bot to use.")
    print()
    print("IMPORTANT: This uses YOUR personal Telegram account, not a bot.")
    print("Messages will be sent from your account.")
    print()

    # Prefer Vault-backed settings (via config.py) over raw env vars.
    # This keeps secrets out of `.env` and centralizes them in Concordia.
    from config import get_settings
    settings = get_settings()

    # Get credentials
    api_id_str = str(settings.telegram_api_id) if settings.telegram_api_id else ""
    if not api_id_str:
        api_id_str = get_env_or_prompt(
            "TELEGRAM_API_ID",
            "Enter your Telegram API ID (from https://my.telegram.org): ",
        )
    try:
        api_id = int(api_id_str)
    except ValueError:
        print("Error: API ID must be a number")
        sys.exit(1)

    api_hash = settings.telegram_api_hash or ""
    if not api_hash:
        api_hash = get_env_or_prompt(
            "TELEGRAM_API_HASH",
            "Enter your Telegram API Hash: ",
        )
    if not api_hash:
        print("Error: API Hash is required")
        sys.exit(1)

    phone = settings.telegram_phone or ""
    if not phone:
        phone = get_env_or_prompt(
            "TELEGRAM_PHONE",
            "Enter your phone number (E.164 format, e.g., +15551234567): ",
        )
    if not phone:
        print("Error: Phone number is required")
        sys.exit(1)

    session_name = os.getenv(
        "TELEGRAM_SESSION_NAME",
        settings.telegram_session_name or "frank_bot",
    )
    data_dir = os.getenv("DATA_DIR", str(ROOT))
    session_base_path = Path(data_dir) / session_name
    session_path = session_base_path.with_suffix(".session")

    print()
    print(f"Session file will be created at: {session_path}")
    print()

    # Create client
    client = TelegramClient(str(session_base_path), api_id, api_hash)

    try:
        await client.connect()

        # Check if already authorized
        if await client.is_user_authorized():
            me = await client.get_me()
            print(f"Already authenticated as: {me.first_name} (@{me.username or 'no username'})")
            print(f"Session file exists: {session_path}")
            print()
            print("Setup complete! No further action needed.")
            return

        # Request verification code
        print("Requesting verification code...")
        print("(Check your Telegram app or phone for the code)")
        print()

        try:
            await client.send_code_request(phone)
        except FloodWaitError as e:
            print(f"Error: Too many requests. Please wait {e.seconds} seconds and try again.")
            sys.exit(1)

        # Get the code from user
        max_attempts = 3
        for attempt in range(max_attempts):
            code = input("Enter the verification code: ").strip()
            if not code:
                print("Error: Code is required")
                continue

            try:
                await client.sign_in(phone, code)
                break
            except PhoneCodeInvalidError:
                remaining = max_attempts - attempt - 1
                if remaining > 0:
                    print(f"Invalid code. {remaining} attempts remaining.")
                else:
                    print("Error: Too many invalid attempts. Please try again later.")
                    sys.exit(1)
            except PhoneCodeExpiredError:
                print("Error: Code expired. Please run the script again to get a new code.")
                sys.exit(1)
            except SessionPasswordNeededError:
                # 2FA is enabled
                print()
                print("Two-factor authentication is enabled on this account.")
                password = get_env_or_prompt(
                    "TELEGRAM_2FA_PASSWORD",
                    "Enter your 2FA password: ",
                    is_secret=True
                )
                try:
                    await client.sign_in(password=password)
                    break
                except Exception as e:
                    print(f"Error: Failed to authenticate with 2FA: {e}")
                    sys.exit(1)

        # Verify authentication
        if await client.is_user_authorized():
            me = await client.get_me()
            print()
            print("=" * 60)
            print("SUCCESS!")
            print("=" * 60)
            print()
            print(f"Authenticated as: {me.first_name} {me.last_name or ''}")
            if me.username:
                print(f"Username: @{me.username}")
            print(f"Phone: {me.phone}")
            print()
            print(f"Session file created: {session_path}")
            print()
            print("Frank Bot can now send and receive Telegram messages on your behalf.")
            print()
            print("IMPORTANT: Keep the .session file secure - it provides access to")
            print("your Telegram account without needing the verification code again.")
            print()
            print("Next: ensure Telegram credentials are stored in Vault at")
            print("  secret/frank-bot/telegram")
            print("and that the service has VAULT_ADDR / VAULT_ROLE_ID / VAULT_SECRET_ID set.")
        else:
            print("Error: Authentication failed. Please check your credentials and try again.")
            sys.exit(1)

    finally:
        await client.disconnect()


def main() -> None:
    """Entry point."""
    try:
        asyncio.run(setup_session())
    except KeyboardInterrupt:
        print("\nSetup cancelled.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
