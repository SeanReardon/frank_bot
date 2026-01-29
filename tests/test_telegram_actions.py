"""
Unit tests for Telegram action handlers.

Tests verify action behavior with mocked TelegramClientService.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from actions.telegram import (
    send_telegram_message,
    get_telegram_messages,
    list_telegram_chats,
)
from services.telegram_client import (
    TelegramMessageResult,
    TelegramMessage,
    TelegramDialog,
)


class TestSendTelegramMessage:
    """Tests for send_telegram_message action."""

    @pytest.mark.asyncio
    async def test_send_message_success(self) -> None:
        """Successfully send a message."""
        mock_result = TelegramMessageResult(
            success=True,
            message_id=12345,
            recipient="@johndoe",
        )

        with patch("actions.telegram.TelegramClientService") as MockService:
            mock_instance = MagicMock()
            mock_instance.is_configured = True
            mock_instance.send_message = AsyncMock(return_value=mock_result)
            MockService.return_value = mock_instance

            result = await send_telegram_message({
                "recipient": "@johndoe",
                "text": "Hello from Frank Bot!",
            })

            assert result["success"] is True
            assert result["recipient"] == "@johndoe"
            assert result["message_id"] == 12345
            assert "Hello from Frank Bot!" in result["text_preview"]
            mock_instance.send_message.assert_called_once_with("@johndoe", "Hello from Frank Bot!")

    @pytest.mark.asyncio
    async def test_send_message_long_text_truncates_preview(self) -> None:
        """Long message text is truncated in preview."""
        long_text = "A" * 150
        mock_result = TelegramMessageResult(
            success=True,
            message_id=12346,
            recipient="@someone",
        )

        with patch("actions.telegram.TelegramClientService") as MockService:
            mock_instance = MagicMock()
            mock_instance.is_configured = True
            mock_instance.send_message = AsyncMock(return_value=mock_result)
            MockService.return_value = mock_instance

            result = await send_telegram_message({
                "recipient": "@someone",
                "text": long_text,
            })

            assert result["success"] is True
            assert result["text_preview"].endswith("...")
            assert len(result["text_preview"]) == 103  # 100 chars + "..."

    @pytest.mark.asyncio
    async def test_send_message_missing_recipient(self) -> None:
        """Raises error when recipient is missing."""
        with pytest.raises(ValueError, match="recipient is required"):
            await send_telegram_message({"text": "Hello"})

    @pytest.mark.asyncio
    async def test_send_message_missing_text(self) -> None:
        """Raises error when text is missing."""
        with pytest.raises(ValueError, match="text is required"):
            await send_telegram_message({"recipient": "@johndoe"})

    @pytest.mark.asyncio
    async def test_send_message_not_configured(self) -> None:
        """Raises error when Telegram is not configured."""
        with patch("actions.telegram.TelegramClientService") as MockService:
            mock_instance = MagicMock()
            mock_instance.is_configured = False
            MockService.return_value = mock_instance

            with pytest.raises(ValueError, match="Telegram is not configured"):
                await send_telegram_message({
                    "recipient": "@johndoe",
                    "text": "Hello",
                })

    @pytest.mark.asyncio
    async def test_send_message_failure(self) -> None:
        """Raises error when send fails."""
        mock_result = TelegramMessageResult(
            success=False,
            message_id=None,
            recipient="@johndoe",
            error="User not found",
        )

        with patch("actions.telegram.TelegramClientService") as MockService:
            mock_instance = MagicMock()
            mock_instance.is_configured = True
            mock_instance.send_message = AsyncMock(return_value=mock_result)
            MockService.return_value = mock_instance

            with pytest.raises(ValueError, match="User not found"):
                await send_telegram_message({
                    "recipient": "@johndoe",
                    "text": "Hello",
                })


class TestGetTelegramMessages:
    """Tests for get_telegram_messages action."""

    @pytest.mark.asyncio
    async def test_get_messages_success(self) -> None:
        """Successfully retrieve messages."""
        mock_messages = [
            TelegramMessage(
                id=1001,
                text="Hello!",
                date="2026-01-29T10:00:00+00:00",
                sender_id=123,
                sender_name="John",
                is_outgoing=False,
            ),
            TelegramMessage(
                id=1002,
                text="Hi there!",
                date="2026-01-29T10:01:00+00:00",
                sender_id=456,
                sender_name="Me",
                is_outgoing=True,
            ),
        ]

        with patch("actions.telegram.TelegramClientService") as MockService:
            mock_instance = MagicMock()
            mock_instance.is_configured = True
            mock_instance.get_messages = AsyncMock(return_value=mock_messages)
            MockService.return_value = mock_instance

            result = await get_telegram_messages({
                "chat": "@johndoe",
                "limit": 10,
            })

            assert result["success"] is True
            assert result["chat"] == "@johndoe"
            assert result["count"] == 2
            assert len(result["messages"]) == 2
            assert result["messages"][0]["id"] == 1001
            assert result["messages"][0]["text"] == "Hello!"
            mock_instance.get_messages.assert_called_once_with("@johndoe", limit=10)

    @pytest.mark.asyncio
    async def test_get_messages_default_limit(self) -> None:
        """Uses default limit when not specified."""
        with patch("actions.telegram.TelegramClientService") as MockService:
            mock_instance = MagicMock()
            mock_instance.is_configured = True
            mock_instance.get_messages = AsyncMock(return_value=[])
            MockService.return_value = mock_instance

            await get_telegram_messages({"chat": "@johndoe"})

            mock_instance.get_messages.assert_called_once_with("@johndoe", limit=20)

    @pytest.mark.asyncio
    async def test_get_messages_limit_clamped(self) -> None:
        """Limit is clamped to 1-100 range."""
        with patch("actions.telegram.TelegramClientService") as MockService:
            mock_instance = MagicMock()
            mock_instance.is_configured = True
            mock_instance.get_messages = AsyncMock(return_value=[])
            MockService.return_value = mock_instance

            # Test upper bound
            await get_telegram_messages({"chat": "@johndoe", "limit": 500})
            mock_instance.get_messages.assert_called_with("@johndoe", limit=100)

            # Test lower bound
            await get_telegram_messages({"chat": "@johndoe", "limit": -5})
            mock_instance.get_messages.assert_called_with("@johndoe", limit=1)

    @pytest.mark.asyncio
    async def test_get_messages_missing_chat(self) -> None:
        """Raises error when chat is missing."""
        with pytest.raises(ValueError, match="chat is required"):
            await get_telegram_messages({})

    @pytest.mark.asyncio
    async def test_get_messages_not_configured(self) -> None:
        """Raises error when Telegram is not configured."""
        with patch("actions.telegram.TelegramClientService") as MockService:
            mock_instance = MagicMock()
            mock_instance.is_configured = False
            MockService.return_value = mock_instance

            with pytest.raises(ValueError, match="Telegram is not configured"):
                await get_telegram_messages({"chat": "@johndoe"})


class TestListTelegramChats:
    """Tests for list_telegram_chats action."""

    @pytest.mark.asyncio
    async def test_list_chats_success(self) -> None:
        """Successfully list chats."""
        mock_dialogs = [
            TelegramDialog(
                id=1001,
                name="John Doe",
                chat_type="user",
                unread_count=3,
                last_message_date="2026-01-29T10:00:00+00:00",
            ),
            TelegramDialog(
                id=-1002,
                name="Family Group",
                chat_type="group",
                unread_count=0,
                last_message_date="2026-01-28T15:00:00+00:00",
            ),
        ]

        with patch("actions.telegram.TelegramClientService") as MockService:
            mock_instance = MagicMock()
            mock_instance.is_configured = True
            mock_instance.get_dialogs = AsyncMock(return_value=mock_dialogs)
            MockService.return_value = mock_instance

            result = await list_telegram_chats({"limit": 10})

            assert result["success"] is True
            assert result["count"] == 2
            assert len(result["chats"]) == 2
            assert result["chats"][0]["id"] == 1001
            assert result["chats"][0]["name"] == "John Doe"
            assert result["chats"][0]["type"] == "user"
            assert result["chats"][1]["type"] == "group"
            mock_instance.get_dialogs.assert_called_once_with(limit=10)

    @pytest.mark.asyncio
    async def test_list_chats_default_limit(self) -> None:
        """Uses default limit when not specified."""
        with patch("actions.telegram.TelegramClientService") as MockService:
            mock_instance = MagicMock()
            mock_instance.is_configured = True
            mock_instance.get_dialogs = AsyncMock(return_value=[])
            MockService.return_value = mock_instance

            await list_telegram_chats({})

            mock_instance.get_dialogs.assert_called_once_with(limit=20)

    @pytest.mark.asyncio
    async def test_list_chats_limit_clamped(self) -> None:
        """Limit is clamped to 1-100 range."""
        with patch("actions.telegram.TelegramClientService") as MockService:
            mock_instance = MagicMock()
            mock_instance.is_configured = True
            mock_instance.get_dialogs = AsyncMock(return_value=[])
            MockService.return_value = mock_instance

            await list_telegram_chats({"limit": 200})
            mock_instance.get_dialogs.assert_called_with(limit=100)

    @pytest.mark.asyncio
    async def test_list_chats_not_configured(self) -> None:
        """Raises error when Telegram is not configured."""
        with patch("actions.telegram.TelegramClientService") as MockService:
            mock_instance = MagicMock()
            mock_instance.is_configured = False
            MockService.return_value = mock_instance

            with pytest.raises(ValueError, match="Telegram is not configured"):
                await list_telegram_chats({})
