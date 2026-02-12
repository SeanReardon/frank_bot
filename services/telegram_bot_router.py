"""
Telegram Bot Router.

Connects inbound Telegram *bot* messages (Bot API) to Frank's jorb system.

This is intentionally separate from the Telethon-based router in
`services/telegram_jorb_router.py`:
- Telethon router listens as Sean's *user account*
- Bot router listens as `@Seans_frank_bot` via Bot API `getUpdates`

The key goal: messages sent to the bot (from an allowlisted username) should
trigger the LLM → script loop and reply back through the bot account.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from services.agent_runner import AgentRunner, IncomingEvent
from services.jorb_storage import JorbContact, JorbStorage
from services.telegram_bot import TelegramBotListener

logger = logging.getLogger(__name__)

# Module-level state
_listener: TelegramBotListener | None = None
_is_initialized: bool = False
_last_error: str | None = None

# Ensure we only process one bot message at a time. (Simple + safe.)
_dispatch_lock = asyncio.Lock()


def _normalize_sender(username: str, sender_name: str | None) -> str:
    username = (username or "").strip()
    if username:
        return f"@{username}"
    return (sender_name or "unknown").strip() or "unknown"


def _build_bot_jorb_plan(
    *,
    text: str,
    username: str,
    chat_id: str,
    sender_name: str,
) -> str:
    # Keep this concise and operational. This is the "task plan" injected
    # into the jorb session system prompt.
    return "\n".join(
        [
            "You are responding to Sean via the Telegram *bot* account.",
            "",
            "Requirements:",
            f"- Reply in the Telegram bot DM chat_id={chat_id!s}.",
            "- Use `frank.telegram_bot.send(...)` for replies (NOT `frank.telegram.send`).",
            "- Use scripts (frank.*) to gather diagnostics/status as needed.",
            "- Keep the final answer concise and directly useful.",
            "- After sending the answer, mark the jorb done.",
            "",
            "Original message:",
            f"- from: @{username} ({sender_name})",
            f"- text: {text}",
        ]
    )


async def _handle_bot_message(
    text: str,
    username: str,
    chat_id: str,
    sender_name: str,
) -> None:
    """
    Handle a single inbound Telegram Bot API message.

    Creates a short-lived jorb for the message and runs the iterative
    script loop so the LLM can gather diagnostics and respond via the bot.
    """
    global _last_error

    async with _dispatch_lock:
        _last_error = None

        sender = _normalize_sender(username, sender_name)
        timestamp = datetime.now(timezone.utc).isoformat()

        storage = JorbStorage()
        runner = AgentRunner(storage=storage)

        if not runner.is_configured:
            # Don't attempt to process without OpenAI configured.
            logger.warning(
                "Telegram bot message received but AgentRunner not configured; "
                "skipping processing"
            )
            return

        # Create a short-lived jorb for this inbound request.
        preview = (text or "").strip().replace("\n", " ")
        if len(preview) > 50:
            preview = preview[:50] + "..."
        jorb_name = f"Bot: {preview}" if preview else "Bot: (empty)"

        plan = _build_bot_jorb_plan(
            text=text,
            username=username,
            chat_id=chat_id,
            sender_name=sender_name,
        )

        # Associate Sean as the contact for routing/history.
        contacts = [
            JorbContact(
                identifier=sender,
                channel="telegram",
                name=sender_name or None,
            )
        ]

        jorb = await storage.create_jorb(
            name=jorb_name,
            plan=plan,
            contacts=contacts,
            personality="default",
        )

        # Mark running so dashboards/filters behave as expected.
        await storage.update_jorb(jorb.id, status="running")

        event = IncomingEvent(
            channel="telegram",
            sender=sender,
            sender_name=sender_name or None,
            content=text,
            timestamp=timestamp,
            message_count=1,
        )

        # Store the inbound message (audit trail).
        await runner.store_inbound_message(jorb.id, event)

        try:
            result = await runner.process_jorb_event(jorb, event=event)
            logger.info(
                "Telegram bot message processed: jorb=%s action=%s success=%s",
                jorb.id,
                result.action_taken,
                result.success,
            )
        except Exception as exc:
            _last_error = str(exc)
            logger.exception("Error processing Telegram bot message: %s", exc)


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
    """Stop the Telegram Bot API listener."""
    global _listener, _is_initialized

    if not _is_initialized:
        return

    if _listener:
        try:
            await _listener.stop_polling()
        except Exception:
            logger.exception("Error stopping Telegram bot listener")

    _listener = None
    _is_initialized = False
    logger.info("Telegram bot router shut down")


def get_bot_router_status() -> dict[str, object]:
    """Return status for diagnostics/system status endpoints."""
    return {
        "initialized": _is_initialized,
        "listener_configured": bool(_listener and _listener.is_configured),
        "listener_running": bool(_listener and _listener.is_running),
        "last_error": _last_error,
    }


__all__ = [
    "initialize_telegram_bot_router",
    "shutdown_telegram_bot_router",
    "get_bot_router_status",
]