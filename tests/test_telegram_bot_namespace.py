"""
Unit tests for TelegramBotNamespace in meta/api.py.

These tests verify that the namespace method correctly wraps the underlying
async action handler with synchronous calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from meta.api import FrankAPI, TelegramBotNamespace


class TestTelegramBotNamespaceSend:
    """Tests for TelegramBotNamespace.send()."""

    def test_send_plain_text_default_target(self) -> None:
        mock_result = {
            "success": True,
            "message_id": 123,
            "chat_id": "999",
        }

        with patch(
            "actions.telegram_bot.send_telegram_bot_message",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result

            ns = TelegramBotNamespace()
            result = ns.send(text="hello")

            mock_action.assert_called_once()
            call_args = mock_action.call_args[0][0]
            assert call_args["text"] == "hello"
            assert call_args["chat_id"] is None
            assert call_args["parse_mode"] is None
            assert result == mock_result

    def test_send_with_chat_id_and_parse_mode(self) -> None:
        mock_result = {"success": True, "message_id": 1, "chat_id": "42"}

        with patch(
            "actions.telegram_bot.send_telegram_bot_message",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result

            ns = TelegramBotNamespace()
            ns.send(text="<b>hi</b>", chat_id="42", parse_mode="HTML")

            call_args = mock_action.call_args[0][0]
            assert call_args["text"] == "<b>hi</b>"
            assert call_args["chat_id"] == "42"
            assert call_args["parse_mode"] == "HTML"


class TestFrankAPITelegramBotIntegration:
    """Tests for FrankAPI.telegram_bot namespace access."""

    def test_frank_api_has_telegram_bot_namespace(self) -> None:
        api = FrankAPI()
        assert hasattr(api, "telegram_bot")
        assert isinstance(api.telegram_bot, TelegramBotNamespace)

    def test_frank_api_telegram_bot_is_same_instance(self) -> None:
        api = FrankAPI()
        assert api.telegram_bot is api.telegram_bot
