"""
Telegram actions: send and receive messages via personal Telegram account.

Uses Telethon library to interact with Telegram through the user's account,
allowing messaging to any Telegram user or group the account can access.
"""

from __future__ import annotations

import logging
from typing import Any

from services.telegram_client import TelegramClientService, TelegramAuthResult

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
        mutual_contacts_only: If true, only include messages from mutual contacts.
                              Outgoing messages are always included. (default false)

    Returns:
        Dict with list of messages and metadata.
    """
    args = arguments or {}
    chat = (args.get("chat") or "").strip()
    limit = args.get("limit", 20)
    mutual_contacts_only = str(args.get("mutual_contacts_only", "")).lower() in ("true", "1", "yes")

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

    messages = await service.get_messages(chat, limit=limit, mutual_contacts_only=mutual_contacts_only)

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
                "is_contact": msg.is_contact,
                "is_mutual_contact": msg.is_mutual_contact,
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
                "is_contact": dialog.is_contact,
                "is_mutual_contact": dialog.is_mutual_contact,
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
    Test the Telegram connection by fetching recent messages with "Magic".

    Returns:
        Dict with connection status and recent conversation with Magic.
        - connected: boolean
        - messages: (only when connected) recent messages from last 24h with Magic
        - error: (only when not connected) error message
    """
    from datetime import datetime, timedelta, timezone

    service = TelegramClientService()

    if not service.is_configured:
        return {
            "connected": False,
            "error": "Telegram is not configured. Set TELEGRAM_API_ID, TELEGRAM_API_HASH, and TELEGRAM_PHONE.",
        }

    try:
        # Fetch messages from "Magic" conversation (last 100 to filter by time)
        messages = await service.get_messages("Magic", limit=100)
        
        # Filter to last 24 hours
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        recent_messages = []
        
        for msg in messages:
            if msg.date:
                # Parse ISO date string
                msg_date = datetime.fromisoformat(msg.date.replace("Z", "+00:00"))
                if msg_date >= cutoff:
                    recent_messages.append({
                        "id": msg.id,
                        "text": msg.text[:200] if msg.text else None,  # Truncate long messages
                        "date": msg.date,
                        "sender": msg.sender_name or ("You" if msg.is_outgoing else "Magic"),
                        "is_outgoing": msg.is_outgoing,
                        "is_contact": msg.is_contact,
                        "is_mutual_contact": msg.is_mutual_contact,
                    })
        
        # Sort by date (oldest first for reading order)
        recent_messages.sort(key=lambda m: m["date"])
        
        return {
            "connected": True,
            "chat_name": "Magic",
            "message_count": len(recent_messages),
            "messages": recent_messages,
        }
    except Exception as exc:
        logger.warning("Error testing Telegram connection: %s", exc)
        return {
            "connected": False,
            "error": str(exc),
        }


async def start_telegram_auth(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Start the Telegram authentication flow by sending a verification code.

    Args (in arguments dict):
        phone: (optional) Phone number in E.164 format. Uses TELEGRAM_PHONE env var if not provided.

    Returns:
        Dict with status and phoneCodeHash for the next step.
        - status: 'code_sent' | 'already_authorized' | 'error'
        - phoneCodeHash: (only when code_sent) Hash needed for verification step
        - error: (only when error) Error message
    """
    args = arguments or {}
    phone = (args.get("phone") or "").strip() or None

    service = TelegramClientService()

    result = await service.send_code_request(phone)

    if result.status == "code_sent":
        return {
            "status": "code_sent",
            "phoneCodeHash": result.phone_code_hash,
        }
    elif result.status == "already_authorized":
        return {"status": "already_authorized"}
    else:
        return {
            "status": "error",
            "error": result.error or "Unknown error",
        }


async def verify_telegram_code(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Verify the Telegram authentication code.

    Args (in arguments dict):
        code: The verification code sent to the phone.
        phoneCodeHash: The hash from the start step.

    Returns:
        Dict with verification status.
        - status: 'success' | 'invalid_code' | 'needs_2fa' | 'error'
        - error: (only when error/invalid_code) Error message
    """
    args = arguments or {}
    code = (args.get("code") or "").strip()
    phone_code_hash = (args.get("phoneCodeHash") or "").strip()

    if not code:
        return {
            "status": "error",
            "error": "code is required.",
        }
    if not phone_code_hash:
        return {
            "status": "error",
            "error": "phoneCodeHash is required.",
        }

    service = TelegramClientService()

    result = await service.sign_in_with_code(code, phone_code_hash)

    if result.status == "success":
        return {"status": "success"}
    elif result.status == "needs_2fa":
        return {"status": "needs_2fa"}
    elif result.status == "invalid_code":
        return {
            "status": "invalid_code",
            "error": result.error or "Invalid verification code.",
        }
    else:
        return {
            "status": "error",
            "error": result.error or "Unknown error",
        }


async def verify_telegram_2fa(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Complete Telegram authentication with 2FA password.

    Args (in arguments dict):
        password: The 2FA password for the account.

    Returns:
        Dict with verification status.
        - status: 'success' | 'invalid_password' | 'error'
        - error: (only when error/invalid_password) Error message
    """
    args = arguments or {}
    password = args.get("password") or ""

    if not password:
        return {
            "status": "error",
            "error": "password is required.",
        }

    service = TelegramClientService()

    result = await service.sign_in_with_2fa(password)

    if result.status == "success":
        return {"status": "success"}
    elif result.status == "invalid_password":
        return {
            "status": "invalid_password",
            "error": result.error or "Invalid password.",
        }
    else:
        return {
            "status": "error",
            "error": result.error or "Unknown error",
        }


__all__ = [
    "send_telegram_message",
    "get_telegram_messages",
    "list_telegram_chats",
    "get_telegram_status",
    "test_telegram_connection",
    "start_telegram_auth",
    "verify_telegram_code",
    "verify_telegram_2fa",
]
