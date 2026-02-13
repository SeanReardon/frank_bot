"""
Telegram Bot Router.

Connects inbound Telegram *bot* messages (Bot API) to Frank's jorb system
via the Switchboard.

This is intentionally separate from the Telethon-based router in
`services/telegram_jorb_router.py`:
- Telethon router listens as Sean's *user account*
- Bot router listens as `@Seans_frank_bot` via Bot API `getUpdates`

Messages from allowlisted senders are buffered (debounced) and then routed
through the Switchboard → AgentRunner pipeline with channel='telegram_bot'.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from services.agent_runner import AgentRunner, IncomingEvent
from services.message_buffer import BufferedEvent, MessageBuffer
from services.telegram_bot import TelegramBotListener

logger = logging.getLogger(__name__)

# Module-level state
_listener: TelegramBotListener | None = None
_message_buffer: MessageBuffer | None = None
_agent_runner: AgentRunner | None = None
_is_initialized: bool = False
_last_error: str | None = None


def _normalize_sender(username: str, sender_name: str | None) -> str:
    username = (username or "").strip()
    if username:
        return f"@{username}"
    return (sender_name or "unknown").strip() or "unknown"


async def _on_bot_message_flush(event: BufferedEvent) -> None:
    """
    Callback fired when the MessageBuffer flushes debounced bot messages.

    Converts the BufferedEvent into an IncomingEvent with
    channel='telegram_bot' and dispatches it through the Switchboard.
    """
    global _agent_runner, _last_error

    if _agent_runner is None:
        _agent_runner = AgentRunner()

    if not _agent_runner.is_configured:
        logger.warning(
            "AgentRunner not configured (missing OpenAI API key); "
            "skipping bot message processing"
        )
        return

    metadata = {
        "source": "telegram_bot",
    }
    if event.metadata:
        metadata["telegram_bot_chat_id"] = event.metadata.get(
            "telegram_bot_chat_id", ""
        )

    incoming_event = IncomingEvent(
        channel="telegram_bot",
        sender=event.sender,
        sender_name=event.sender_name,
        content=event.content,
        timestamp=event.timestamp,
        metadata=metadata,
        message_count=event.message_count,
    )

    logger.info(
        "Processing debounced bot message from %s (%d messages combined)",
        event.sender,
        event.message_count,
    )

    try:
        result = await _agent_runner.process_incoming_message(incoming_event)
        _last_error = None
        logger.info(
            "Bot message processed: jorb=%s action=%s success=%s",
            result.jorb_id,
            result.action_taken,
            result.success,
        )
    except Exception as exc:
        _last_error = str(exc)
        logger.exception("Error processing bot message: %s", exc)


def _get_message_buffer() -> MessageBuffer:
    """Get or create the module-level message buffer."""
    global _message_buffer

    if _message_buffer is None:
        _message_buffer = MessageBuffer(on_flush=_on_bot_message_flush)

    return _message_buffer


async def _handle_bot_message(
    text: str,
    username: str,
    chat_id: str,
    sender_name: str,
) -> None:
    """
    Handle a single inbound Telegram Bot API message.

    Buffers the message for debouncing; the flush callback will
    route it through Switchboard → AgentRunner.
    """
    sender = _normalize_sender(username, sender_name)
    timestamp = datetime.now(timezone.utc).isoformat()

    message_buffer = _get_message_buffer()
    await message_buffer.buffer_message(
        channel="telegram_bot",
        sender=sender,
        content=text,
        sender_name=sender_name or None,
        timestamp=timestamp,
        metadata={
            "telegram_bot_chat_id": str(chat_id),
        },
    )

    logger.info(
        "Buffered bot message from %s (chat_id=%s) for processing",
        sender,
        chat_id,
    )


async def initialize_telegram_bot_router() -> bool:
    """
    Start the Telegram Bot API listener (getUpdates long-polling).

    Returns:
        True if listener started (or already running), False otherwise.
    """
    global _listener, _is_initialized, _last_error

    if _is_initialized:
        logger.debug("Telegram bot router already initialized")
        return True

    # Listener callback signature: (text, username, chat_id, sender_name)
    _listener = TelegramBotListener(on_message=_handle_bot_message)

    if not _listener.is_configured:
        logger.warning("Telegram bot not configured; bot router not initialized")
        _last_error = "not_configured"
        _listener = None
        _is_initialized = False
        return False

    try:
        await _listener.start_polling()
        _is_initialized = True
        _last_error = None
        logger.info("Telegram bot router initialized successfully")
        return True
    except Exception as exc:
        _last_error = str(exc)
        logger.exception("Failed to start Telegram bot listener: %s", exc)
        _listener = None
        _is_initialized = False
        return False


async def shutdown_telegram_bot_router() -> None:
    """Stop the Telegram Bot API listener and flush pending messages."""
    global _listener, _message_buffer, _is_initialized

    if not _is_initialized:
        return

    if _listener:
        try:
            await _listener.stop_polling()
        except Exception:
            logger.exception("Error stopping Telegram bot listener")

    if _message_buffer:
        await _message_buffer.flush_all()

    _listener = None
    _is_initialized = False
    logger.info("Telegram bot router shut down")


def get_bot_router_status() -> dict[str, object]:
    """Return status for diagnostics/system status endpoints."""
    return {
        "initialized": _is_initialized,
        "listener_configured": bool(_listener and _listener.is_configured),
        "listener_running": bool(_listener and _listener.is_running),
        "pending_messages": sum(
            1 for _ in (_message_buffer._buffers if _message_buffer else {})
        ),
        "last_error": _last_error,
    }


__all__ = [
    "initialize_telegram_bot_router",
    "shutdown_telegram_bot_router",
    "get_bot_router_status",
]
