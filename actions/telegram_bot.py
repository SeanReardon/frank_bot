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
            "error": "Telegram bot is not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_CHAT_ID.",
        }

    result = await bot.send_notification(
        "🧪 <b>Test Notification</b>\n\nThis is a test message from Frank Bot dashboard.",
        parse_mode="HTML",
    )

    if result.success:
        return {"success": True}
    else:
        return {"success": False, "error": result.error}


__all__ = ["get_telegram_bot_status", "test_telegram_bot"]
