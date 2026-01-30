"""
Telegram Jorb Router for connecting Telegram messages to jorb processing.

Routes incoming Telegram messages through the MessageBuffer for debouncing,
then dispatches to AgentRunner for processing.
"""

from __future__ import annotations

import logging
from datetime import timezone

from telethon import events
from telethon.tl.types import User

from services.agent_runner import AgentRunner, IncomingEvent
from services.jorb_storage import JorbContact, JorbStorage
from services.message_buffer import BufferedEvent, MessageBuffer
from services.telegram_client import TelegramClientService

logger = logging.getLogger(__name__)

# Module-level instances
_message_buffer: MessageBuffer | None = None
_agent_runner: AgentRunner | None = None
_telegram_service: TelegramClientService | None = None
_is_initialized: bool = False


async def _on_telegram_buffer_flush(event: BufferedEvent) -> None:
    """
    Callback called when the message buffer flushes Telegram messages.

    Routes debounced messages to the AgentRunner for processing.
    """
    global _agent_runner

    if _agent_runner is None:
        _agent_runner = AgentRunner()

    if not _agent_runner.is_configured:
        logger.warning("AgentRunner not configured (no OPENAI_API_KEY), skipping jorb processing")
        return

    # Convert BufferedEvent to IncomingEvent
    incoming_event = IncomingEvent(
        channel="telegram",
        sender=event.sender,
        sender_name=event.sender_name,
        content=event.content,
        timestamp=event.timestamp,
        message_count=event.message_count,
    )

    logger.info(
        "Processing debounced Telegram message from %s (%d messages combined)",
        event.sender,
        event.message_count,
    )

    try:
        result = await _agent_runner.process_incoming_message(incoming_event)
        logger.info(
            "AgentRunner result for Telegram from %s: jorb=%s, action=%s, success=%s",
            event.sender,
            result.jorb_id,
            result.action_taken,
            result.success,
        )
    except Exception as exc:
        logger.error("Error processing Telegram message through AgentRunner: %s", exc)


def _get_message_buffer() -> MessageBuffer:
    """Get or create the module-level message buffer."""
    global _message_buffer

    if _message_buffer is None:
        _message_buffer = MessageBuffer(on_flush=_on_telegram_buffer_flush)

    return _message_buffer


async def _is_jorb_contact(username: str | None, name: str | None) -> bool:
    """
    Check if a Telegram user is in any active jorb's contacts.

    Uses username or name for matching (not phone numbers).

    Args:
        username: Telegram username (without @)
        name: Full name of the user

    Returns:
        True if the user is in an active jorb's contacts
    """
    storage = JorbStorage()
    open_jorbs = await storage.list_jorbs(status_filter="open")

    for jorb in open_jorbs:
        for contact in jorb.contacts:
            if contact.channel != "telegram":
                continue

            # Match by username (case-insensitive, strip @ prefix)
            identifier = contact.identifier.lstrip("@").lower()
            if username and identifier == username.lower():
                return True

            # Match by name if no username
            if name and contact.name and contact.name.lower() == name.lower():
                return True

    return False


async def _handle_telegram_message(event: events.NewMessage.Event) -> None:
    """
    Handle an incoming Telegram message event.

    This is the callback registered with TelegramClientService.
    Messages are only processed if from a jorb contact.

    Args:
        event: Telethon NewMessage.Event
    """
    # Get sender info
    sender = await event.get_sender()
    logger.info(
        "Telegram message handler invoked: sender=%s, type=%s, text=%s",
        sender,
        type(sender).__name__ if sender else "None",
        (event.message.text or "")[:50],
    )
    if sender is None:
        logger.info("Skipping message with no sender")
        return
    
    # Accept both User and bots (bots are also User type in Telethon but have bot=True)
    if not isinstance(sender, User):
        logger.info("Skipping message - sender is not User type: %s", type(sender).__name__)
        return

    # Extract sender details
    username = sender.username or ""
    name = sender.first_name or ""
    if sender.last_name:
        name = f"{name} {sender.last_name}".strip()

    # Use username as identifier, falling back to user ID
    sender_identifier = f"@{username}" if username else str(sender.id)

    # Check if sender is in any jorb's contacts
    is_jorb_participant = await _is_jorb_contact(username, name)

    if not is_jorb_participant:
        logger.debug(
            "Skipping Telegram message from %s (not a jorb contact)",
            sender_identifier,
        )
        return

    # Get message text
    message_text = event.message.text or ""
    if not message_text:
        logger.debug("Skipping Telegram message with no text content")
        return

    # Get timestamp
    timestamp = event.message.date
    if timestamp:
        timestamp_str = timestamp.astimezone(timezone.utc).isoformat()
    else:
        from datetime import datetime
        timestamp_str = datetime.now(timezone.utc).isoformat()

    # Buffer the message for debouncing
    message_buffer = _get_message_buffer()
    await message_buffer.buffer_message(
        channel="telegram",
        sender=sender_identifier,
        content=message_text,
        sender_name=name or None,
        timestamp=timestamp_str,
    )

    logger.info(
        "Buffered Telegram message from %s (%s) for jorb processing",
        name or sender_identifier,
        sender_identifier,
    )


async def initialize_telegram_jorb_router() -> bool:
    """
    Initialize the Telegram-to-jorb message router.

    Sets up the TelegramClientService to listen for incoming messages
    and route them through the MessageBuffer to AgentRunner.

    Returns:
        True if initialization was successful, False otherwise
    """
    global _telegram_service, _is_initialized

    if _is_initialized:
        logger.debug("Telegram jorb router already initialized")
        return True

    _telegram_service = TelegramClientService()

    if not _telegram_service.is_configured:
        logger.warning("Telegram not configured, jorb router not initialized")
        return False

    try:
        # Connect to Telegram
        await _telegram_service.connect()

        # Register our message handler
        _telegram_service.register_message_handler(_handle_telegram_message)

        # Start listening for messages
        await _telegram_service.start_listening()

        _is_initialized = True
        logger.info("Telegram jorb router initialized successfully")
        return True

    except Exception as exc:
        logger.error("Failed to initialize Telegram jorb router: %s", exc)
        return False


async def shutdown_telegram_jorb_router() -> None:
    """
    Shut down the Telegram jorb router.

    Stops listening for messages and cleans up resources.
    """
    global _telegram_service, _message_buffer, _is_initialized

    if not _is_initialized:
        return

    if _telegram_service:
        await _telegram_service.stop_listening()
        _telegram_service.unregister_message_handler(_handle_telegram_message)

    if _message_buffer:
        # Flush any pending messages before shutdown
        await _message_buffer.flush_all()

    _is_initialized = False
    logger.info("Telegram jorb router shut down")


def get_router_status() -> dict:
    """
    Get the current status of the Telegram jorb router.

    Returns:
        Dict with status information
    """
    global _telegram_service, _message_buffer, _is_initialized, _agent_runner

    return {
        "initialized": _is_initialized,
        "telegram_configured": _telegram_service.is_configured if _telegram_service else False,
        "agent_configured": _agent_runner.is_configured if _agent_runner else False,
        "pending_messages": sum(
            _message_buffer.get_pending_count(key.split(":")[1], "telegram")
            for key in getattr(_message_buffer, "_buffers", {}).keys()
            if key.startswith("telegram:")
        ) if _message_buffer else 0,
    }


__all__ = [
    "initialize_telegram_jorb_router",
    "shutdown_telegram_jorb_router",
    "get_router_status",
    "_handle_telegram_message",
    "_is_jorb_contact",
]
