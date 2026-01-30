"""
Telegram client service using Telethon for user account messaging.

This service wraps the Telethon library to provide Telegram messaging
capabilities from the user's personal account (not a bot).

Uses a singleton pattern with asyncio lock to prevent SQLite database
locking issues from concurrent access to the session file.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass

from telethon import TelegramClient, events
from telethon.errors import (
    FloodWaitError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PasswordHashInvalidError,
    SessionPasswordNeededError,
    UserNotMutualContactError,
)
from telethon.tl.types import Channel, Chat, User

from typing import Callable, Coroutine, Any

from config import get_settings
from services.stats import stats

logger = logging.getLogger(__name__)

# Module-level singleton client and lock to prevent concurrent access
_shared_client: TelegramClient | None = None
_client_lock = asyncio.Lock()
# Registered message handlers for real-time message processing
_message_handlers: list[Callable[[events.NewMessage.Event], Coroutine[Any, Any, None]]] = []
_handler_registered: bool = False


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
    is_contact: bool = False
    is_mutual_contact: bool = False


@dataclass
class TelegramDialog:
    """A Telegram conversation/chat."""

    id: int
    name: str
    chat_type: str  # 'user', 'group', 'channel'
    unread_count: int
    last_message_date: str | None
    is_contact: bool = False
    is_mutual_contact: bool = False


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
    """Service for sending and receiving Telegram messages via user account.
    
    Uses a module-level singleton client with asyncio locking to prevent
    SQLite database locking issues from concurrent access.
    """

    def __init__(self):
        settings = get_settings()
        self._api_id = settings.telegram_api_id
        self._api_hash = settings.telegram_api_hash
        self._phone = settings.telegram_phone
        self._session_name = settings.telegram_session_name
        self._session_path = _get_session_path(self._session_name)

    @property
    def is_configured(self) -> bool:
        """Check if the service has required configuration."""
        return bool(self._api_id and self._api_hash and self._phone)

    @property
    def session_file_path(self) -> str:
        """Return the path to the session file (including .session extension)."""
        return f"{self._session_path}.session"

    async def _get_shared_client(self) -> TelegramClient:
        """Get or create the shared client instance with proper locking."""
        global _shared_client
        
        async with _client_lock:
            if _shared_client is not None and _shared_client.is_connected():
                return _shared_client
            
            if not self.is_configured:
                raise ValueError(
                    "Telegram is not configured. Set TELEGRAM_API_ID, "
                    "TELEGRAM_API_HASH, and TELEGRAM_PHONE."
                )
            
            # Disconnect old client if exists but not connected
            if _shared_client is not None:
                try:
                    await _shared_client.disconnect()
                except Exception:
                    pass
            
            _shared_client = TelegramClient(
                self._session_path,
                self._api_id,
                self._api_hash,
            )
            await _shared_client.connect()
            logger.info("Telegram shared client connected")
            return _shared_client

    async def connect(self) -> None:
        """Initialize and start the Telethon client."""
        client = await self._get_shared_client()
        
        if not await client.is_user_authorized():
            raise ValueError(
                "Telegram session not authorized. Run the setup script: "
                "poetry run python scripts/setup_telegram_session.py"
            )

        logger.info("Telegram client connected and authorized")

    async def disconnect(self) -> None:
        """Cleanly shut down the shared client."""
        global _shared_client

        async with _client_lock:
            if _shared_client is not None:
                await _shared_client.disconnect()
                _shared_client = None
                logger.info("Telegram client disconnected")

    def register_message_handler(
        self,
        handler: Callable[[events.NewMessage.Event], Coroutine[Any, Any, None]],
    ) -> None:
        """
        Register a callback to receive incoming Telegram messages in real-time.

        The callback will be called with Telethon NewMessage.Event objects
        for all incoming messages (not outgoing).

        Note: Only messages from mutual contacts will be processed by the
        internal handler to maintain security.

        Args:
            handler: Async function that receives NewMessage.Event
        """
        global _message_handlers
        _message_handlers.append(handler)
        logger.info("Registered Telegram message handler (total: %d)", len(_message_handlers))

    def unregister_message_handler(
        self,
        handler: Callable[[events.NewMessage.Event], Coroutine[Any, Any, None]],
    ) -> bool:
        """
        Unregister a previously registered message handler.

        Args:
            handler: The handler to remove

        Returns:
            True if the handler was found and removed, False otherwise
        """
        global _message_handlers
        try:
            _message_handlers.remove(handler)
            logger.info("Unregistered Telegram message handler (total: %d)", len(_message_handlers))
            return True
        except ValueError:
            return False

    async def _dispatch_to_handlers(self, event: events.NewMessage.Event) -> None:
        """Internal handler that dispatches to all registered handlers."""
        global _message_handlers

        # Only process incoming messages (not outgoing)
        if event.out:
            return

        # Get sender info
        sender = await event.get_sender()
        if sender is None:
            logger.debug("Skipping message with no sender")
            return

        # Only process messages from mutual contacts or bots (security gate)
        if isinstance(sender, User):
            # Allow bots (they have sender.bot=True) and mutual contacts
            is_bot = getattr(sender, 'bot', False)
            is_mutual = getattr(sender, 'mutual_contact', False)
            if not (is_bot or is_mutual):
                logger.debug(
                    "Skipping message from non-mutual contact: %s",
                    sender.first_name or sender.id,
                )
                return
        else:
            # Skip groups/channels
            logger.debug("Skipping message from non-user entity: %s", type(sender).__name__)
            return

        logger.info(
            "Dispatching Telegram message from %s (%s) to %d handlers",
            sender.first_name or sender.id,
            sender.username or "no username",
            len(_message_handlers),
        )

        # Dispatch to all registered handlers
        for handler in _message_handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.error("Error in Telegram message handler: %s", e)

    async def start_listening(self) -> None:
        """
        Start listening for incoming messages.

        Must be called after connect() to begin receiving real-time messages.
        Messages will be dispatched to all registered handlers.
        """
        global _handler_registered

        client = await self._get_shared_client()

        if _handler_registered:
            logger.debug("Message handler already registered with client")
            return

        # Register the internal dispatcher with the client
        client.add_event_handler(
            self._dispatch_to_handlers,
            events.NewMessage(incoming=True),
        )
        _handler_registered = True
        logger.info("Started listening for Telegram messages")

    async def stop_listening(self) -> None:
        """
        Stop listening for incoming messages.

        Removes the event handler from the client.
        """
        global _handler_registered, _shared_client

        if not _handler_registered or _shared_client is None:
            return

        _shared_client.remove_event_handler(
            self._dispatch_to_handlers,
            events.NewMessage(incoming=True),
        )
        _handler_registered = False
        logger.info("Stopped listening for Telegram messages")

    async def _ensure_connected(self) -> TelegramClient:
        """Ensure client is connected and return it."""
        return await self._get_shared_client()

    def session_file_exists(self) -> bool:
        """Check if the session file exists."""
        return os.path.exists(self.session_file_path)

    async def is_authorized(self) -> bool:
        """
        Check if the session is authorized.

        Returns True if the session file exists and is authorized.
        Uses the shared client to prevent database locking issues.
        """
        if not self.is_configured:
            return False

        if not self.session_file_exists():
            return False

        try:
            client = await self._get_shared_client()
            authorized = await client.is_user_authorized()
            return authorized
        except Exception as exc:
            logger.warning("Error checking authorization: %s", exc)
            return False

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
        mutual_contacts_only: bool = False,
    ) -> list[TelegramMessage]:
        """
        Retrieve recent messages from a chat.

        Args:
            chat_id: Username, phone, or numeric chat ID.
            limit: Maximum number of messages to retrieve.
            mutual_contacts_only: If True, only include messages from mutual contacts.
                                  Outgoing messages are always included.

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
                is_contact = False
                is_mutual_contact = False
                if message.sender:
                    sender_id = message.sender.id
                    if isinstance(message.sender, User):
                        sender_name = message.sender.first_name
                        if message.sender.last_name:
                            sender_name += f" {message.sender.last_name}"
                        # Capture contact relationship flags
                        is_contact = message.sender.contact or False
                        is_mutual_contact = message.sender.mutual_contact or False
                    else:
                        sender_name = getattr(message.sender, "title", str(sender_id))

                msg = TelegramMessage(
                    id=message.id,
                    text=message.text,
                    date=message.date.isoformat() if message.date else None,
                    sender_id=sender_id,
                    sender_name=sender_name,
                    is_outgoing=message.out,
                    is_contact=is_contact,
                    is_mutual_contact=is_mutual_contact,
                )

                # Apply mutual contact filter if requested
                # Always include outgoing messages (from us)
                if mutual_contacts_only and not msg.is_outgoing and not msg.is_mutual_contact:
                    logger.debug(
                        "Filtering out message %s from non-mutual contact %s",
                        msg.id,
                        sender_name or sender_id,
                    )
                    continue

                messages.append(msg)

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

    async def is_mutual_contact(self, chat_id: str | int) -> bool:
        """
        Check if a chat/user is a mutual contact.

        This is the gating check for whether frank_bot should process
        messages from this user. Only mutual contacts get LLM attention.

        Args:
            chat_id: Username, phone, or numeric chat ID.

        Returns:
            True if the user is a mutual contact, False otherwise.
            Returns False for groups/channels (not applicable).
        """
        client = await self._ensure_connected()

        try:
            entity = await client.get_entity(chat_id)

            if isinstance(entity, User):
                is_mutual = entity.mutual_contact or False
                logger.debug(
                    "Contact check for %s (%s): mutual=%s",
                    entity.first_name,
                    chat_id,
                    is_mutual,
                )
                return is_mutual

            # Groups and channels are not "contacts"
            return False

        except Exception as exc:
            logger.warning("Error checking mutual contact status for %s: %s", chat_id, exc)
            return False

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
                # Determine chat type and contact status
                entity = dialog.entity
                is_contact = False
                is_mutual_contact = False

                if isinstance(entity, User):
                    chat_type = "user"
                    is_contact = entity.contact or False
                    is_mutual_contact = entity.mutual_contact or False
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
                        is_contact=is_contact,
                        is_mutual_contact=is_mutual_contact,
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

        try:
            client = await self._get_shared_client()

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

        try:
            client = await self._get_shared_client()

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

        try:
            client = await self._get_shared_client()

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


__all__ = [
    "TelegramClientService",
    "TelegramMessageResult",
    "TelegramMessage",
    "TelegramDialog",
    "TelegramAuthResult",
]
