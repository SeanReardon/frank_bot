"""
Telegram Bot action handlers for notification service status.

These endpoints are for the web dashboard to check the configuration
status of the Telegram Bot notification service and test it.
"""

from __future__ import annotations

from typing import Any

from config import get_settings
from services.telegram_bot import TelegramBot


async def get_telegram_bot_status(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Get the configuration status of the Telegram Bot notification service.

    Returns:
        dict with:
            - configured: bool - whether bot token and chat ID are set
            - chatId: str | None - the configured chat ID (if configured)
    """
    settings = get_settings()
    configured = bool(settings.telegram_bot_token and settings.telegram_bot_chat_id)

    result: dict[str, Any] = {"configured": configured}
    if configured:
        result["chatId"] = settings.telegram_bot_chat_id

    return result


async def test_telegram_bot(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Send a test notification via the Telegram Bot.

    Returns:
        dict with:
            - success: bool - whether the test message was sent
            - error: str | None - error message if failed
    """
    bot = TelegramBot()

    if not bot.is_configured:
        return {
            "success": False,
            "error": (
                "Telegram bot is not configured. "
                "Configure Vault secret `secret/frank-bot/telegram-bot` "
                "(token, chat_id), or for local/dev runs without Vault set "
                "TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_CHAT_ID."
            ),
        }

    result = await bot.send_notification(
        "🧪 <b>Test Notification</b>\n\nThis is a test message from Frank Bot dashboard.",
        parse_mode="HTML",
    )

    if result.success:
        return {"success": True}
    else:
        return {"success": False, "error": result.error}


async def send_telegram_bot_message(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Send a Telegram message via the bot (Bot API).

    This is intended for scripts/jorbs that need to reply to Sean using
    `@Seans_frank_bot` rather than Telethon (personal account).

    Args (in arguments dict):
        text: Message content to send (required)
        chat_id: Optional override chat ID (defaults to TELEGRAM_BOT_CHAT_ID)
        parse_mode: Optional Telegram parse mode (e.g. "HTML", "MarkdownV2").
                    If omitted/null, message is sent as plain text.

    Returns:
        dict with:
            - success: bool
            - message_id: int | None
            - chat_id: str | None
            - error: str | None
    """
    args = arguments or {}

    text = (args.get("text") or args.get("message") or "").strip()
    if not text:
        raise ValueError("text is required.")

    chat_id = (args.get("chat_id") or args.get("chatId") or "")
    chat_id = str(chat_id).strip() if chat_id is not None else ""
    chat_id = chat_id or None

    parse_mode = args.get("parse_mode") or args.get("parseMode")
    parse_mode = str(parse_mode).strip() if parse_mode is not None else ""
    parse_mode = parse_mode or None

    settings = get_settings()
    if not settings.telegram_bot_token:
        return {
            "success": False,
            "message_id": None,
            "chat_id": chat_id or settings.telegram_bot_chat_id,
            "error": (
                "Telegram bot is not configured. "
                "Configure Vault secret `secret/frank-bot/telegram-bot` "
                "(token, chat_id), or for local/dev runs without Vault set "
                "TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_CHAT_ID."
            ),
        }

    # Prefer explicit chat_id override; fall back to configured chat ID.
    target_chat_id = chat_id or settings.telegram_bot_chat_id
    if not target_chat_id:
        return {
            "success": False,
            "message_id": None,
            "chat_id": None,
            "error": (
                "Telegram bot chat_id is not configured. "
                "Set Vault secret `secret/frank-bot/telegram-bot` (chat_id) "
                "or provide chat_id explicitly."
            ),
        }

    bot = TelegramBot(token=settings.telegram_bot_token, chat_id=target_chat_id)
    result = await bot.send_notification(
        text,
        # Default to plain text when not specified.
        parse_mode=parse_mode,
        chat_id=target_chat_id,
    )

    if result.success:
        return {
            "success": True,
            "message_id": result.message_id,
            "chat_id": target_chat_id,
        }

    return {
        "success": False,
        "message_id": None,
        "chat_id": target_chat_id,
        "error": result.error,
    }


async def telegram_send_photo_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Send a photo via the Telegram user account (Telethon).

    Args (in arguments dict):
        recipient: Username or phone number (required)
        photo_path: Path to image file on disk (required, must be in allowed dirs)
        caption: Optional caption for the photo

    Returns:
        dict with:
            - success: bool
            - message_id: int | None
            - error: str | None
    """
    from services.telegram_client import TelegramClientService

    args = arguments or {}

    recipient = (args.get("recipient") or "").strip()
    if not recipient:
        raise ValueError("'recipient' is required")

    photo_path = (args.get("photo_path") or "").strip()
    if not photo_path:
        raise ValueError("'photo_path' is required")

    caption = args.get("caption")
    if caption:
        caption = str(caption).strip() or None

    client_service = TelegramClientService()
    result = await client_service.send_photo(
        recipient=recipient,
        photo_path=photo_path,
        caption=caption,
    )

    if result.success:
        return {
            "success": True,
            "message_id": result.message_id,
        }

    return {
        "success": False,
        "message_id": None,
        "error": result.error,
    }


__all__ = [
    "get_telegram_bot_status",
    "test_telegram_bot",
    "send_telegram_bot_message",
    "telegram_send_photo_action",
]
