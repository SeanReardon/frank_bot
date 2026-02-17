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

import asyncio
import logging
import os
import re
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
_last_processed_at: str | None = None
_last_processed_sender: str | None = None
_last_processed_preview: str | None = None
_last_processing_result: dict[str, object] | None = None


def _normalize_sender(username: str, sender_name: str | None) -> str:
    username = (username or "").strip()
    if username:
        return f"@{username}"
    return (sender_name or "unknown").strip() or "unknown"


_ANDROID_SCREEN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^/screen(?:@\w+)?\b", re.IGNORECASE),
    re.compile(r"^/screenshot(?:@\w+)?\b", re.IGNORECASE),
    re.compile(r"\bshow\s+me\s+(?:the\s+)?android\s+screen\b", re.IGNORECASE),
    re.compile(r"\bandroid\s+screenshot\b", re.IGNORECASE),
)


def _is_android_screen_request(text: str) -> bool:
    normalized = (text or "").strip()
    if not normalized:
        return False
    return any(p.search(normalized) for p in _ANDROID_SCREEN_PATTERNS)


async def _send_android_screen_via_bot(chat_id: str) -> bool:
    """
    Take an Android screenshot and send it to the requesting Telegram chat.

    This bypasses Switchboard/AgentRunner entirely: it's a deterministic command.
    """
    from config import get_settings
    from services.android_client import AndroidClient
    from services.telegram_bot import TelegramBot

    settings = get_settings()
    if not settings.telegram_bot_token:
        logger.warning("Telegram bot token not configured; cannot send screenshot")
        return False

    bot = TelegramBot(token=settings.telegram_bot_token, chat_id=chat_id)
    client = AndroidClient()

    async def _capture_once() -> tuple[str, str | None]:
        r = await client.take_screenshot()
        if not r.success or not r.output:
            return "", r.error or r.output or "unknown adb error"
        return r.output.strip(), None

    def _file_size(path: str) -> int:
        try:
            if path and os.path.exists(path):
                return int(os.path.getsize(path))
        except Exception:
            pass
        return 0

    async def _recover_and_recapture_if_blank(path: str) -> str:
        """
        If the screenshot looks blank (tiny PNG), try a best-effort recovery:
        wake -> unlock -> HOME -> recapture.
        """
        if _file_size(path) >= 50_000:
            return path

        logger.warning(
            "Android screenshot looks blank (bytes=%s); attempting recovery capture",
            _file_size(path),
        )
        try:
            await client.wake_device()
            await client.unlock_device()
            await client.press_key("home")
            await asyncio.sleep(0.6)
        except Exception as exc:
            logger.warning("Recovery actions failed before recapture: %s", exc)

        new_path, _err = await _capture_once()
        return new_path or path

    path, err = await _capture_once()
    if not path:
        await bot.send_notification(
            f"Failed to take screenshot: {err}",
            parse_mode=None,
            chat_id=chat_id,
        )
        return False

    path = await _recover_and_recapture_if_blank(path)

    # If still tiny, it's probably an "empty" capture (screen off / secure app).
    if 0 < _file_size(path) < 50_000:
        await bot.send_notification(
            "Screenshot captured but looks blank (black). This usually means the "
            "screen is off/locked, or the foreground app blocks screenshots. "
            "Try unlocking the phone or switching to the home screen, then retry /screen.",
            parse_mode=None,
            chat_id=chat_id,
        )

    caption = f"Android screen @ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')}"
    send_res = await bot.send_photo(path, caption=caption, chat_id=chat_id)

    # Best-effort cleanup of the local temp file.
    try:
        if path.startswith("/tmp/") and os.path.exists(path):
            os.remove(path)
    except Exception:
        logger.debug("Failed to clean up screenshot temp file: %s", path)

    if not send_res.success:
        await bot.send_notification(
            f"Screenshot captured but failed to send via Telegram: {send_res.error}",
            parse_mode=None,
            chat_id=chat_id,
        )
        return False

    return True


async def _on_bot_message_flush(event: BufferedEvent) -> None:
    """
    Callback fired when the MessageBuffer flushes debounced bot messages.

    Converts the BufferedEvent into an IncomingEvent with
    channel='telegram_bot' and dispatches it through the Switchboard.
    """
    global _agent_runner, _last_error
    global _last_processed_at, _last_processed_sender, _last_processed_preview, _last_processing_result

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

    _last_processed_at = datetime.now(timezone.utc).isoformat()
    _last_processed_sender = event.sender
    preview = (event.content or "").strip().replace("\n", " ")
    if len(preview) > 200:
        preview = preview[:200] + "..."
    _last_processed_preview = preview

    try:
        result = await _agent_runner.process_incoming_message(incoming_event)
        _last_error = None
        _last_processing_result = {
            "jorb_id": result.jorb_id,
            "action_taken": result.action_taken,
            "success": result.success,
            "message_sent": result.message_sent,
            "error": result.error,
        }
        logger.info(
            "Bot message processed: jorb=%s action=%s success=%s",
            result.jorb_id,
            result.action_taken,
            result.success,
        )
    except Exception as exc:
        _last_error = str(exc)
        _last_processing_result = {
            "jorb_id": None,
            "action_taken": "error",
            "success": False,
            "message_sent": False,
            "error": str(exc),
        }
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
    # Deterministic command: bypass the LLM path.
    if _is_android_screen_request(text):
        try:
            ok = await _send_android_screen_via_bot(chat_id=str(chat_id))
            logger.info("Handled android screen request via bot (ok=%s)", ok)
        except Exception as exc:
            logger.exception("Failed handling android screen request: %s", exc)
        return

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
    status: dict[str, object] = {
        "initialized": _is_initialized,
        "listener_configured": bool(_listener and _listener.is_configured),
        "listener_running": bool(_listener and _listener.is_running),
        "pending_messages": sum(
            1 for _ in (_message_buffer._buffers if _message_buffer else {})
        ),
        "agent_runner_configured": bool(_agent_runner and _agent_runner.is_configured),
        "last_processed_at": _last_processed_at,
        "last_processed_sender": _last_processed_sender,
        "last_processed_preview": _last_processed_preview,
        "last_processing_result": _last_processing_result,
        "last_error": _last_error,
    }

    if _listener is not None:
        try:
            status["listener_status"] = _listener.get_status()
        except Exception:
            # Defensive: never break diagnostics
            status["listener_status"] = {"error": "failed_to_get_listener_status"}

    return status


__all__ = [
    "initialize_telegram_bot_router",
    "shutdown_telegram_bot_router",
    "get_bot_router_status",
]
