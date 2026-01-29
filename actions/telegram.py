"""
Telegram actions: send and receive messages via personal Telegram account.

Uses Telethon library to interact with Telegram through the user's account,
allowing messaging to any Telegram user or group the account can access.
"""

from __future__ import annotations

import logging
from typing import Any

from services.telegram_client import TelegramClientService

logger = logging.getLogger(__name__)


async def send_telegram_message(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Send a Telegram message to a user or chat.

    Args (in arguments dict):
        recipient: Username (with or without @), phone number, or chat ID.
        text: The message text to send.

    Returns:
        Dict with success status and message details.
    """
    args = arguments or {}
    recipient = (args.get("recipient") or "").strip()
    text = (args.get("text") or "").strip()

    if not recipient:
        raise ValueError("recipient is required (username, phone number, or chat ID).")
    if not text:
        raise ValueError("text is required.")

    service = TelegramClientService()

    if not service.is_configured:
        raise ValueError(
            "Telegram is not configured. "
            "Please set TELEGRAM_API_ID, TELEGRAM_API_HASH, and TELEGRAM_PHONE."
        )

    result = await service.send_message(recipient, text)

    if result.success:
        return {
            "message": f"Message sent to {recipient}",
            "success": True,
            "recipient": recipient,
            "message_id": result.message_id,
            "text_preview": text[:100] + ("..." if len(text) > 100 else ""),
        }
    else:
        raise ValueError(f"Failed to send Telegram message: {result.error}")


async def get_telegram_messages(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Retrieve recent messages from a Telegram chat.

    Args (in arguments dict):
        chat: Username, phone number, or chat ID to get messages from.
        limit: Maximum number of messages to retrieve (default 20, max 100).

    Returns:
        Dict with list of messages and metadata.
    """
    args = arguments or {}
    chat = (args.get("chat") or "").strip()
    limit = args.get("limit", 20)

    if not chat:
        raise ValueError("chat is required (username, phone number, or chat ID).")

    # Validate and constrain limit
    try:
        limit = int(limit)
    except (ValueError, TypeError):
        limit = 20
    limit = max(1, min(100, limit))

    service = TelegramClientService()

    if not service.is_configured:
        raise ValueError(
            "Telegram is not configured. "
            "Please set TELEGRAM_API_ID, TELEGRAM_API_HASH, and TELEGRAM_PHONE."
        )

    messages = await service.get_messages(chat, limit=limit)

    return {
        "success": True,
        "chat": chat,
        "count": len(messages),
        "messages": [
            {
                "id": msg.id,
                "text": msg.text,
                "date": msg.date,
                "sender_id": msg.sender_id,
                "sender_name": msg.sender_name,
                "is_outgoing": msg.is_outgoing,
            }
            for msg in messages
        ],
    }


async def list_telegram_chats(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    List recent Telegram conversations.

    Args (in arguments dict):
        limit: Maximum number of chats to retrieve (default 20, max 100).

    Returns:
        Dict with list of chats and metadata.
    """
    args = arguments or {}
    limit = args.get("limit", 20)

    # Validate and constrain limit
    try:
        limit = int(limit)
    except (ValueError, TypeError):
        limit = 20
    limit = max(1, min(100, limit))

    service = TelegramClientService()

    if not service.is_configured:
        raise ValueError(
            "Telegram is not configured. "
            "Please set TELEGRAM_API_ID, TELEGRAM_API_HASH, and TELEGRAM_PHONE."
        )

    dialogs = await service.get_dialogs(limit=limit)

    return {
        "success": True,
        "count": len(dialogs),
        "chats": [
            {
                "id": dialog.id,
                "name": dialog.name,
                "type": dialog.chat_type,
                "unread_count": dialog.unread_count,
                "last_message_date": dialog.last_message_date,
            }
            for dialog in dialogs
        ],
    }


async def get_telegram_status(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Get the current Telegram connection status.

    Returns:
        Dict with status and optional account info.
        - status: 'not_configured' | 'needs_auth' | 'connected'
        - account: (only when connected) { name, username, phone }
    """
    service = TelegramClientService()

    # Check if required env vars are configured
    if not service.is_configured:
        return {"status": "not_configured"}

    # Check if session exists and is authorized
    try:
        authorized = await service.is_authorized()
    except Exception as exc:
        logger.warning("Error checking Telegram auth status: %s", exc)
        authorized = False

    if not authorized:
        return {"status": "needs_auth"}

    # Get account info
    try:
        account_info = await service.get_me()
        return {
            "status": "connected",
            "account": account_info,
        }
    except Exception as exc:
        logger.warning("Error getting Telegram account info: %s", exc)
        return {
            "status": "connected",
            "account": None,
        }


async def test_telegram_connection(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Test the Telegram connection by fetching recent dialogs.

    Returns:
        Dict with connection status and first 3 chats.
        - connected: boolean
        - dialogs: (only when connected) first 3 chat names
        - error: (only when not connected) error message
    """
    service = TelegramClientService()

    if not service.is_configured:
        return {
            "connected": False,
            "error": "Telegram is not configured. Set TELEGRAM_API_ID, TELEGRAM_API_HASH, and TELEGRAM_PHONE.",
        }

    try:
        dialogs = await service.get_dialogs(limit=3)
        return {
            "connected": True,
            "dialogs": [
                {"id": d.id, "name": d.name, "type": d.chat_type}
                for d in dialogs
            ],
        }
    except Exception as exc:
        logger.warning("Error testing Telegram connection: %s", exc)
        return {
            "connected": False,
            "error": str(exc),
        }


__all__ = [
    "send_telegram_message",
    "get_telegram_messages",
    "list_telegram_chats",
    "get_telegram_status",
    "test_telegram_connection",
]
