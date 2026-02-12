"""
Tests for Telegram Bot action handlers.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestGetTelegramBotStatus:
    """Tests for get_telegram_bot_status action."""

    @pytest.mark.asyncio
    async def test_configured_returns_true_with_chat_id(self) -> None:
        """Returns configured: true and chatId when both are set."""
        mock_settings = MagicMock()
        mock_settings.telegram_bot_token = "123456:ABC-DEF"
        mock_settings.telegram_bot_chat_id = "987654321"

        with patch("actions.telegram_bot.get_settings", return_value=mock_settings):
            from actions.telegram_bot import get_telegram_bot_status

            result = await get_telegram_bot_status()

            assert result == {
                "configured": True,
                "chatId": "987654321",
            }

    @pytest.mark.asyncio
    async def test_not_configured_without_token(self) -> None:
        """Returns configured: false when token is missing."""
        mock_settings = MagicMock()
        mock_settings.telegram_bot_token = None
        mock_settings.telegram_bot_chat_id = "987654321"

        with patch("actions.telegram_bot.get_settings", return_value=mock_settings):
            from actions.telegram_bot import get_telegram_bot_status

            result = await get_telegram_bot_status()

            assert result == {"configured": False}

    @pytest.mark.asyncio
    async def test_not_configured_without_chat_id(self) -> None:
        """Returns configured: false when chat_id is missing."""
        mock_settings = MagicMock()
        mock_settings.telegram_bot_token = "123456:ABC-DEF"
        mock_settings.telegram_bot_chat_id = None

        with patch("actions.telegram_bot.get_settings", return_value=mock_settings):
            from actions.telegram_bot import get_telegram_bot_status

            result = await get_telegram_bot_status()

            assert result == {"configured": False}

    @pytest.mark.asyncio
    async def test_not_configured_without_both(self) -> None:
        """Returns configured: false when both are missing."""
        mock_settings = MagicMock()
        mock_settings.telegram_bot_token = None
        mock_settings.telegram_bot_chat_id = None

        with patch("actions.telegram_bot.get_settings", return_value=mock_settings):
            from actions.telegram_bot import get_telegram_bot_status

            result = await get_telegram_bot_status()

            assert result == {"configured": False}


class TestTestTelegramBot:
    """Tests for test_telegram_bot action."""

    @pytest.mark.asyncio
    async def test_success_when_configured(self) -> None:
        """Returns success: true when notification is sent."""
        mock_result = MagicMock()
        mock_result.success = True

        mock_bot = MagicMock()
        mock_bot.is_configured = True
        mock_bot.send_notification = AsyncMock(return_value=mock_result)

        with patch("actions.telegram_bot.TelegramBot", return_value=mock_bot):
            from actions.telegram_bot import test_telegram_bot

            result = await test_telegram_bot()

            assert result == {"success": True}
            mock_bot.send_notification.assert_called_once()

    @pytest.mark.asyncio
    async def test_failure_when_not_configured(self) -> None:
        """Returns error when bot is not configured."""
        mock_bot = MagicMock()
        mock_bot.is_configured = False

        with patch("actions.telegram_bot.TelegramBot", return_value=mock_bot):
            from actions.telegram_bot import test_telegram_bot

            result = await test_telegram_bot()

            assert result["success"] is False
            assert "not configured" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_failure_when_send_fails(self) -> None:
        """Returns error when notification fails to send."""
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error = "Connection failed"

        mock_bot = MagicMock()
        mock_bot.is_configured = True
        mock_bot.send_notification = AsyncMock(return_value=mock_result)

        with patch("actions.telegram_bot.TelegramBot", return_value=mock_bot):
            from actions.telegram_bot import test_telegram_bot

            result = await test_telegram_bot()

            assert result == {"success": False, "error": "Connection failed"}


class TestSendTelegramBotMessage:
    """Tests for send_telegram_bot_message action."""

    @pytest.mark.asyncio
    async def test_requires_text(self) -> None:
        with patch("actions.telegram_bot.get_settings", return_value=MagicMock()):
            from actions.telegram_bot import send_telegram_bot_message

            with pytest.raises(ValueError):
                await send_telegram_bot_message({"text": ""})

    @pytest.mark.asyncio
    async def test_not_configured_returns_error(self) -> None:
        mock_settings = MagicMock()
        mock_settings.telegram_bot_token = None
        mock_settings.telegram_bot_chat_id = "123"

        with patch("actions.telegram_bot.get_settings", return_value=mock_settings):
            from actions.telegram_bot import send_telegram_bot_message

            result = await send_telegram_bot_message({"text": "hi"})
            assert result["success"] is False
            assert "not configured" in (result.get("error") or "").lower()

    @pytest.mark.asyncio
    async def test_requires_chat_id_when_missing(self) -> None:
        mock_settings = MagicMock()
        mock_settings.telegram_bot_token = "token"
        mock_settings.telegram_bot_chat_id = None

        with patch("actions.telegram_bot.get_settings", return_value=mock_settings):
            from actions.telegram_bot import send_telegram_bot_message

            result = await send_telegram_bot_message({"text": "hi"})
            assert result["success"] is False
            assert "chat_id" in (result.get("error") or "").lower()

    @pytest.mark.asyncio
    async def test_sends_message_with_override_chat_id(self) -> None:
        mock_settings = MagicMock()
        mock_settings.telegram_bot_token = "token"
        mock_settings.telegram_bot_chat_id = "default"

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.message_id = 777
        mock_result.error = None

        mock_bot = MagicMock()
        mock_bot.send_notification = AsyncMock(return_value=mock_result)

        with patch(
            "actions.telegram_bot.get_settings",
            return_value=mock_settings,
        ), patch(
            "actions.telegram_bot.TelegramBot",
            return_value=mock_bot,
        ):
            from actions.telegram_bot import send_telegram_bot_message

            result = await send_telegram_bot_message(
                {"text": "hello", "chat_id": "42", "parse_mode": None}
            )

            assert result == {"success": True, "message_id": 777, "chat_id": "42"}
            mock_bot.send_notification.assert_called_once()
