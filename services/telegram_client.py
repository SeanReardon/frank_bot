"""
Telegram client service using Telethon for user account messaging.

This service wraps the Telethon library to provide Telegram messaging
capabilities from the user's personal account (not a bot).
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass

from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PasswordHashInvalidError,
    SessionPasswordNeededError,
    UserNotMutualContactError,
)
from telethon.tl.types import Channel, Chat, User

from config import get_settings
from services.stats import stats

logger = logging.getLogger(__name__)


@dataclass
class TelegramMessageResult:
    """Result of a Telegram message operation."""

    success: bool
    message_id: int | None
    recipient: str
    error: str | None = None


@dataclass
class TelegramMessage:
    """A Telegram message from a chat."""

    id: int
    text: str | None
    date: str
    sender_id: int | None
    sender_name: str | None
    is_outgoing: bool


@dataclass
class TelegramDialog:
    """A Telegram conversation/chat."""

    id: int
    name: str
    chat_type: str  # 'user', 'group', 'channel'
    unread_count: int
    last_message_date: str | None


@dataclass
class TelegramAuthResult:
    """Result of a Telegram authentication operation."""

    status: str  # 'code_sent', 'already_authorized', 'success', 'needs_2fa', 'invalid_code', 'invalid_password', 'error'
    phone_code_hash: str | None = None
    error: str | None = None


def _get_session_path(session_name: str) -> str:
    """
    Construct the full path to the Telegram session file.

    Uses DATA_DIR environment variable if set, otherwise defaults to
    current directory. This allows session files to be stored on
    mounted volumes in containerized deployments.
    """
    data_dir = os.getenv("DATA_DIR") or "."
    return os.path.join(data_dir, session_name)


class TelegramClientService:
    """Service for sending and receiving Telegram messages via user account."""

    def __init__(self):
        settings = get_settings()
        self._api_id = settings.telegram_api_id
        self._api_hash = settings.telegram_api_hash
        self._phone = settings.telegram_phone
        self._session_name = settings.telegram_session_name
        self._session_path = _get_session_path(self._session_name)
        self._client: TelegramClient | None = None

    @property
    def is_configured(self) -> bool:
        """Check if the service has required configuration."""
        return bool(self._api_id and self._api_hash and self._phone)

    @property
    def session_file_path(self) -> str:
        """Return the path to the session file (including .session extension)."""
        return f"{self._session_path}.session"

    async def connect(self) -> None:
        """Initialize and start the Telethon client."""
        if not self.is_configured:
            raise ValueError(
                "Telegram is not configured. Set TELEGRAM_API_ID, "
                "TELEGRAM_API_HASH, and TELEGRAM_PHONE."
            )

        if self._client is not None and self._client.is_connected():
            return

        self._client = TelegramClient(
            self._session_path,
            self._api_id,
            self._api_hash,
        )
        await self._client.connect()

        if not await self._client.is_user_authorized():
            raise ValueError(
                "Telegram session not authorized. Run the setup script: "
                "poetry run python scripts/setup_telegram_session.py"
            )

        logger.info("Telegram client connected successfully")

    async def disconnect(self) -> None:
        """Cleanly shut down the client."""
        if self._client is not None:
            await self._client.disconnect()
            self._client = None
            logger.info("Telegram client disconnected")

    async def _ensure_connected(self) -> TelegramClient:
        """Ensure client is connected and return it."""
        if self._client is None or not self._client.is_connected():
            await self.connect()
        return self._client

    def session_file_exists(self) -> bool:
        """Check if the session file exists."""
        return os.path.exists(self.session_file_path)

    async def is_authorized(self) -> bool:
        """
        Check if the session is authorized.

        Returns True if the session file exists and is authorized.
        Does not require full connection for status check.
        """
        if not self.is_configured:
            return False

        if not self.session_file_exists():
            return False

        # Create a temporary client to check authorization
        client = TelegramClient(
            self._session_path,
            self._api_id,
            self._api_hash,
        )
        try:
            await client.connect()
            authorized = await client.is_user_authorized()
            return authorized
        except Exception as exc:
            logger.warning("Error checking authorization: %s", exc)
            return False
        finally:
            await client.disconnect()

    async def get_me(self) -> dict | None:
        """
        Get information about the authenticated user.

        Returns a dict with name, username, and phone, or None if not connected.
        """
        try:
            client = await self._ensure_connected()
            me = await client.get_me()
            if me is None:
                return None

            name = me.first_name or ""
            if me.last_name:
                name = f"{name} {me.last_name}".strip()

            return {
                "name": name or None,
                "username": me.username,
                "phone": me.phone,
            }
        except Exception as exc:
            logger.warning("Error getting user info: %s", exc)
            return None

    async def send_message(
        self,
        recipient: str,
        text: str,
    ) -> TelegramMessageResult:
        """
        Send a message to a user/bot by username or phone number.

        Args:
            recipient: Username (with or without @) or phone number in E.164 format.
            text: The message text to send.

        Returns:
            TelegramMessageResult with success status and message details.
        """
        if not self.is_configured:
            return TelegramMessageResult(
                success=False,
                message_id=None,
                recipient=recipient,
                error="Telegram is not configured. Check TELEGRAM_API_ID, "
                "TELEGRAM_API_HASH, and TELEGRAM_PHONE.",
            )

        tg_stats = stats.get_service_stats("telegram")
        start = time.time()

        try:
            client = await self._ensure_connected()
            logger.info("Sending Telegram message to %s", recipient)

            message = await client.send_message(recipient, text)
            elapsed_ms = (time.time() - start) * 1000
            tg_stats.record_request(elapsed_ms, success=True)

            logger.info("Telegram message sent successfully, id=%s", message.id)

            return TelegramMessageResult(
                success=True,
                message_id=message.id,
                recipient=recipient,
            )

        except FloodWaitError as exc:
            elapsed_ms = (time.time() - start) * 1000
            error_msg = f"Rate limited. Please wait {exc.seconds} seconds."
            tg_stats.record_request(elapsed_ms, success=False, error=error_msg)
            stats.record_error(
                "telegram",
                error_msg,
                {"method": "send_message", "to": recipient},
            )
            logger.error("Telegram rate limit: %s", error_msg)

            return TelegramMessageResult(
                success=False,
                message_id=None,
                recipient=recipient,
                error=error_msg,
            )

        except (UserNotMutualContactError, ValueError) as exc:
            elapsed_ms = (time.time() - start) * 1000
            error_msg = f"Recipient not found or not accessible: {exc}"
            tg_stats.record_request(elapsed_ms, success=False, error=error_msg)
            stats.record_error(
                "telegram",
                error_msg,
                {"method": "send_message", "to": recipient},
            )
            logger.error("Telegram recipient error: %s", error_msg)

            return TelegramMessageResult(
                success=False,
                message_id=None,
                recipient=recipient,
                error=error_msg,
            )

        except Exception as exc:
            elapsed_ms = (time.time() - start) * 1000
            error_msg = str(exc)
            tg_stats.record_request(elapsed_ms, success=False, error=error_msg)
            stats.record_error(
                "telegram",
                error_msg,
                {"method": "send_message", "to": recipient},
            )
            logger.exception("Unexpected error sending Telegram message to %s", recipient)

            return TelegramMessageResult(
                success=False,
                message_id=None,
                recipient=recipient,
                error=error_msg,
            )

    async def get_messages(
        self,
        chat_id: str | int,
        limit: int = 20,
    ) -> list[TelegramMessage]:
        """
        Retrieve recent messages from a chat.

        Args:
            chat_id: Username, phone, or numeric chat ID.
            limit: Maximum number of messages to retrieve.

        Returns:
            List of TelegramMessage objects.
        """
        client = await self._ensure_connected()
        tg_stats = stats.get_service_stats("telegram")
        start = time.time()

        try:
            messages = []
            async for message in client.iter_messages(chat_id, limit=limit):
                sender_name = None
                sender_id = None
                if message.sender:
                    sender_id = message.sender.id
                    if isinstance(message.sender, User):
                        sender_name = message.sender.first_name
                        if message.sender.last_name:
                            sender_name += f" {message.sender.last_name}"
                    else:
                        sender_name = getattr(message.sender, "title", str(sender_id))

                messages.append(
                    TelegramMessage(
                        id=message.id,
                        text=message.text,
                        date=message.date.isoformat() if message.date else None,
                        sender_id=sender_id,
                        sender_name=sender_name,
                        is_outgoing=message.out,
                    )
                )

            elapsed_ms = (time.time() - start) * 1000
            tg_stats.record_request(elapsed_ms, success=True)
            return messages

        except Exception as exc:
            elapsed_ms = (time.time() - start) * 1000
            error_msg = str(exc)
            tg_stats.record_request(elapsed_ms, success=False, error=error_msg)
            stats.record_error(
                "telegram",
                error_msg,
                {"method": "get_messages", "chat_id": str(chat_id)},
            )
            logger.exception("Error getting messages from %s", chat_id)
            raise

    async def get_dialogs(
        self,
        limit: int = 20,
    ) -> list[TelegramDialog]:
        """
        List recent conversations with metadata.

        Args:
            limit: Maximum number of dialogs to retrieve.

        Returns:
            List of TelegramDialog objects.
        """
        client = await self._ensure_connected()
        tg_stats = stats.get_service_stats("telegram")
        start = time.time()

        try:
            dialogs = []
            async for dialog in client.iter_dialogs(limit=limit):
                # Determine chat type
                entity = dialog.entity
                if isinstance(entity, User):
                    chat_type = "user"
                elif isinstance(entity, Channel):
                    chat_type = "channel" if entity.broadcast else "supergroup"
                elif isinstance(entity, Chat):
                    chat_type = "group"
                else:
                    chat_type = "unknown"

                last_date = None
                if dialog.message and dialog.message.date:
                    last_date = dialog.message.date.isoformat()

                dialogs.append(
                    TelegramDialog(
                        id=dialog.id,
                        name=dialog.name or str(dialog.id),
                        chat_type=chat_type,
                        unread_count=dialog.unread_count,
                        last_message_date=last_date,
                    )
                )

            elapsed_ms = (time.time() - start) * 1000
            tg_stats.record_request(elapsed_ms, success=True)
            return dialogs

        except Exception as exc:
            elapsed_ms = (time.time() - start) * 1000
            error_msg = str(exc)
            tg_stats.record_request(elapsed_ms, success=False, error=error_msg)
            stats.record_error(
                "telegram",
                error_msg,
                {"method": "get_dialogs"},
            )
            logger.exception("Error getting dialogs")
            raise

    async def mark_read(
        self,
        chat_id: str | int,
    ) -> bool:
        """
        Mark messages as read in a chat.

        Args:
            chat_id: Username, phone, or numeric chat ID.

        Returns:
            True if successful.
        """
        client = await self._ensure_connected()
        tg_stats = stats.get_service_stats("telegram")
        start = time.time()

        try:
            await client.send_read_acknowledge(chat_id)
            elapsed_ms = (time.time() - start) * 1000
            tg_stats.record_request(elapsed_ms, success=True)
            logger.info("Marked messages as read in %s", chat_id)
            return True

        except Exception as exc:
            elapsed_ms = (time.time() - start) * 1000
            error_msg = str(exc)
            tg_stats.record_request(elapsed_ms, success=False, error=error_msg)
            stats.record_error(
                "telegram",
                error_msg,
                {"method": "mark_read", "chat_id": str(chat_id)},
            )
            logger.exception("Error marking messages as read in %s", chat_id)
            raise

    async def send_code_request(
        self,
        phone: str | None = None,
    ) -> TelegramAuthResult:
        """
        Start the authentication flow by sending a verification code.

        Args:
            phone: Phone number to authenticate. Uses env var if not provided.

        Returns:
            TelegramAuthResult with status and phone_code_hash.
        """
        phone = phone or self._phone

        if not phone:
            return TelegramAuthResult(
                status="error",
                error="Phone number is required. Provide it or set TELEGRAM_PHONE.",
            )

        if not self._api_id or not self._api_hash:
            return TelegramAuthResult(
                status="error",
                error="Telegram API credentials not configured. Set TELEGRAM_API_ID and TELEGRAM_API_HASH.",
            )

        # Create a new client for auth flow
        client = TelegramClient(
            self._session_path,
            self._api_id,
            self._api_hash,
        )

        try:
            await client.connect()

            # Check if already authorized
            if await client.is_user_authorized():
                return TelegramAuthResult(status="already_authorized")

            # Send the code
            result = await client.send_code_request(phone)
            logger.info("Telegram verification code sent to %s", phone)

            return TelegramAuthResult(
                status="code_sent",
                phone_code_hash=result.phone_code_hash,
            )

        except FloodWaitError as exc:
            logger.warning("Telegram rate limit on send_code_request: %s", exc)
            return TelegramAuthResult(
                status="error",
                error=f"Rate limited. Please wait {exc.seconds} seconds.",
            )

        except Exception as exc:
            logger.exception("Error sending Telegram verification code")
            return TelegramAuthResult(
                status="error",
                error=str(exc),
            )

        finally:
            # Don't disconnect - keep session file for next step
            pass

    async def sign_in_with_code(
        self,
        code: str,
        phone_code_hash: str,
        phone: str | None = None,
    ) -> TelegramAuthResult:
        """
        Complete authentication with the verification code.

        Args:
            code: The verification code sent to the phone.
            phone_code_hash: The hash from send_code_request().
            phone: Phone number. Uses env var if not provided.

        Returns:
            TelegramAuthResult with status ('success', 'needs_2fa', 'invalid_code', 'error').
        """
        phone = phone or self._phone

        if not phone:
            return TelegramAuthResult(
                status="error",
                error="Phone number is required.",
            )

        if not self._api_id or not self._api_hash:
            return TelegramAuthResult(
                status="error",
                error="Telegram API credentials not configured.",
            )

        client = TelegramClient(
            self._session_path,
            self._api_id,
            self._api_hash,
        )

        try:
            await client.connect()

            # Check if already authorized
            if await client.is_user_authorized():
                return TelegramAuthResult(status="success")

            # Try to sign in with the code
            await client.sign_in(
                phone=phone,
                code=code,
                phone_code_hash=phone_code_hash,
            )

            logger.info("Telegram authentication successful for %s", phone)
            return TelegramAuthResult(status="success")

        except SessionPasswordNeededError:
            logger.info("Telegram 2FA required for %s", phone)
            return TelegramAuthResult(status="needs_2fa")

        except PhoneCodeInvalidError:
            logger.warning("Invalid Telegram verification code for %s", phone)
            return TelegramAuthResult(
                status="invalid_code",
                error="The verification code is invalid.",
            )

        except PhoneCodeExpiredError:
            logger.warning("Telegram verification code expired for %s", phone)
            return TelegramAuthResult(
                status="invalid_code",
                error="The verification code has expired. Please request a new code.",
            )

        except Exception as exc:
            logger.exception("Error during Telegram sign in")
            return TelegramAuthResult(
                status="error",
                error=str(exc),
            )

        finally:
            await client.disconnect()

    async def sign_in_with_2fa(
        self,
        password: str,
    ) -> TelegramAuthResult:
        """
        Complete 2FA authentication with the account password.

        Args:
            password: The 2FA password.

        Returns:
            TelegramAuthResult with status ('success', 'invalid_password', 'error').
        """
        if not self._api_id or not self._api_hash:
            return TelegramAuthResult(
                status="error",
                error="Telegram API credentials not configured.",
            )

        client = TelegramClient(
            self._session_path,
            self._api_id,
            self._api_hash,
        )

        try:
            await client.connect()

            # Check if already authorized
            if await client.is_user_authorized():
                return TelegramAuthResult(status="success")

            # Sign in with 2FA password
            await client.sign_in(password=password)

            logger.info("Telegram 2FA authentication successful")
            return TelegramAuthResult(status="success")

        except PasswordHashInvalidError:
            logger.warning("Invalid Telegram 2FA password")
            return TelegramAuthResult(
                status="invalid_password",
                error="The password is incorrect.",
            )

        except Exception as exc:
            logger.exception("Error during Telegram 2FA sign in")
            return TelegramAuthResult(
                status="error",
                error=str(exc),
            )

        finally:
            await client.disconnect()


__all__ = [
    "TelegramClientService",
    "TelegramMessageResult",
    "TelegramMessage",
    "TelegramDialog",
    "TelegramAuthResult",
]
