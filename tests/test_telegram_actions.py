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
    get_telegram_status,
    test_telegram_connection,
    start_telegram_auth,
    verify_telegram_code,
    verify_telegram_2fa,
)
from services.telegram_client import (
    TelegramMessageResult,
    TelegramMessage,
    TelegramDialog,
    TelegramAuthResult,
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


class TestGetTelegramStatus:
    """Tests for get_telegram_status action."""

    @pytest.mark.asyncio
    async def test_status_not_configured(self) -> None:
        """Returns not_configured when env vars are missing."""
        with patch("actions.telegram.TelegramClientService") as MockService:
            mock_instance = MagicMock()
            mock_instance.is_configured = False
            MockService.return_value = mock_instance

            result = await get_telegram_status({})

            assert result["status"] == "not_configured"
            assert "account" not in result

    @pytest.mark.asyncio
    async def test_status_needs_auth(self) -> None:
        """Returns needs_auth when session is not authorized."""
        with patch("actions.telegram.TelegramClientService") as MockService:
            mock_instance = MagicMock()
            mock_instance.is_configured = True
            mock_instance.is_authorized = AsyncMock(return_value=False)
            MockService.return_value = mock_instance

            result = await get_telegram_status({})

            assert result["status"] == "needs_auth"
            assert "account" not in result

    @pytest.mark.asyncio
    async def test_status_connected(self) -> None:
        """Returns connected with account info when authorized."""
        with patch("actions.telegram.TelegramClientService") as MockService:
            mock_instance = MagicMock()
            mock_instance.is_configured = True
            mock_instance.is_authorized = AsyncMock(return_value=True)
            mock_instance.get_me = AsyncMock(return_value={
                "name": "John Doe",
                "username": "johndoe",
                "phone": "+15551234567",
            })
            MockService.return_value = mock_instance

            result = await get_telegram_status({})

            assert result["status"] == "connected"
            assert result["account"]["name"] == "John Doe"
            assert result["account"]["username"] == "johndoe"
            assert result["account"]["phone"] == "+15551234567"

    @pytest.mark.asyncio
    async def test_status_connected_no_account_info(self) -> None:
        """Returns connected even if get_me fails."""
        with patch("actions.telegram.TelegramClientService") as MockService:
            mock_instance = MagicMock()
            mock_instance.is_configured = True
            mock_instance.is_authorized = AsyncMock(return_value=True)
            mock_instance.get_me = AsyncMock(side_effect=Exception("Connection error"))
            MockService.return_value = mock_instance

            result = await get_telegram_status({})

            assert result["status"] == "connected"
            assert result["account"] is None


class TestTestTelegramConnection:
    """Tests for test_telegram_connection action."""

    @pytest.mark.asyncio
    async def test_connection_not_configured(self) -> None:
        """Returns not connected when env vars are missing."""
        with patch("actions.telegram.TelegramClientService") as MockService:
            mock_instance = MagicMock()
            mock_instance.is_configured = False
            MockService.return_value = mock_instance

            result = await test_telegram_connection({})

            assert result["connected"] is False
            assert "error" in result

    @pytest.mark.asyncio
    async def test_connection_success(self) -> None:
        """Returns connected with dialogs when successful."""
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

            result = await test_telegram_connection({})

            assert result["connected"] is True
            assert len(result["dialogs"]) == 2
            assert result["dialogs"][0]["name"] == "John Doe"
            mock_instance.get_dialogs.assert_called_once_with(limit=3)

    @pytest.mark.asyncio
    async def test_connection_failure(self) -> None:
        """Returns not connected with error when connection fails."""
        with patch("actions.telegram.TelegramClientService") as MockService:
            mock_instance = MagicMock()
            mock_instance.is_configured = True
            mock_instance.get_dialogs = AsyncMock(side_effect=Exception("Connection failed"))
            MockService.return_value = mock_instance

            result = await test_telegram_connection({})

            assert result["connected"] is False
            assert "Connection failed" in result["error"]


class TestStartTelegramAuth:
    """Tests for start_telegram_auth action."""

    @pytest.mark.asyncio
    async def test_auth_start_code_sent(self) -> None:
        """Returns code_sent with phoneCodeHash when successful."""
        mock_result = TelegramAuthResult(
            status="code_sent",
            phone_code_hash="abc123hash",
        )

        with patch("actions.telegram.TelegramClientService") as MockService:
            mock_instance = MagicMock()
            mock_instance.send_code_request = AsyncMock(return_value=mock_result)
            MockService.return_value = mock_instance

            result = await start_telegram_auth({"phone": "+15551234567"})

            assert result["status"] == "code_sent"
            assert result["phoneCodeHash"] == "abc123hash"
            mock_instance.send_code_request.assert_called_once_with("+15551234567")

    @pytest.mark.asyncio
    async def test_auth_start_already_authorized(self) -> None:
        """Returns already_authorized when already logged in."""
        mock_result = TelegramAuthResult(status="already_authorized")

        with patch("actions.telegram.TelegramClientService") as MockService:
            mock_instance = MagicMock()
            mock_instance.send_code_request = AsyncMock(return_value=mock_result)
            MockService.return_value = mock_instance

            result = await start_telegram_auth({})

            assert result["status"] == "already_authorized"

    @pytest.mark.asyncio
    async def test_auth_start_uses_default_phone(self) -> None:
        """Uses env var phone when not provided."""
        mock_result = TelegramAuthResult(status="code_sent", phone_code_hash="hash123")

        with patch("actions.telegram.TelegramClientService") as MockService:
            mock_instance = MagicMock()
            mock_instance.send_code_request = AsyncMock(return_value=mock_result)
            MockService.return_value = mock_instance

            await start_telegram_auth({})

            # Called with None, which means use default
            mock_instance.send_code_request.assert_called_once_with(None)

    @pytest.mark.asyncio
    async def test_auth_start_error(self) -> None:
        """Returns error status on failure."""
        mock_result = TelegramAuthResult(
            status="error",
            error="Rate limited. Please wait 300 seconds.",
        )

        with patch("actions.telegram.TelegramClientService") as MockService:
            mock_instance = MagicMock()
            mock_instance.send_code_request = AsyncMock(return_value=mock_result)
            MockService.return_value = mock_instance

            result = await start_telegram_auth({})

            assert result["status"] == "error"
            assert "Rate limited" in result["error"]


class TestVerifyTelegramCode:
    """Tests for verify_telegram_code action."""

    @pytest.mark.asyncio
    async def test_verify_success(self) -> None:
        """Returns success when code is valid."""
        mock_result = TelegramAuthResult(status="success")

        with patch("actions.telegram.TelegramClientService") as MockService:
            mock_instance = MagicMock()
            mock_instance.sign_in_with_code = AsyncMock(return_value=mock_result)
            MockService.return_value = mock_instance

            result = await verify_telegram_code({
                "code": "12345",
                "phoneCodeHash": "abc123hash",
            })

            assert result["status"] == "success"
            mock_instance.sign_in_with_code.assert_called_once_with("12345", "abc123hash")

    @pytest.mark.asyncio
    async def test_verify_needs_2fa(self) -> None:
        """Returns needs_2fa when 2FA is required."""
        mock_result = TelegramAuthResult(status="needs_2fa")

        with patch("actions.telegram.TelegramClientService") as MockService:
            mock_instance = MagicMock()
            mock_instance.sign_in_with_code = AsyncMock(return_value=mock_result)
            MockService.return_value = mock_instance

            result = await verify_telegram_code({
                "code": "12345",
                "phoneCodeHash": "abc123hash",
            })

            assert result["status"] == "needs_2fa"

    @pytest.mark.asyncio
    async def test_verify_invalid_code(self) -> None:
        """Returns invalid_code when code is wrong."""
        mock_result = TelegramAuthResult(
            status="invalid_code",
            error="The verification code is invalid.",
        )

        with patch("actions.telegram.TelegramClientService") as MockService:
            mock_instance = MagicMock()
            mock_instance.sign_in_with_code = AsyncMock(return_value=mock_result)
            MockService.return_value = mock_instance

            result = await verify_telegram_code({
                "code": "00000",
                "phoneCodeHash": "abc123hash",
            })

            assert result["status"] == "invalid_code"
            assert "invalid" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_verify_missing_code(self) -> None:
        """Returns error when code is missing."""
        result = await verify_telegram_code({
            "phoneCodeHash": "abc123hash",
        })

        assert result["status"] == "error"
        assert "code is required" in result["error"]

    @pytest.mark.asyncio
    async def test_verify_missing_hash(self) -> None:
        """Returns error when phoneCodeHash is missing."""
        result = await verify_telegram_code({
            "code": "12345",
        })

        assert result["status"] == "error"
        assert "phoneCodeHash is required" in result["error"]


class TestVerifyTelegram2FA:
    """Tests for verify_telegram_2fa action."""

    @pytest.mark.asyncio
    async def test_2fa_success(self) -> None:
        """Returns success when password is correct."""
        mock_result = TelegramAuthResult(status="success")

        with patch("actions.telegram.TelegramClientService") as MockService:
            mock_instance = MagicMock()
            mock_instance.sign_in_with_2fa = AsyncMock(return_value=mock_result)
            MockService.return_value = mock_instance

            result = await verify_telegram_2fa({"password": "secretpassword"})

            assert result["status"] == "success"
            mock_instance.sign_in_with_2fa.assert_called_once_with("secretpassword")

    @pytest.mark.asyncio
    async def test_2fa_invalid_password(self) -> None:
        """Returns invalid_password when password is wrong."""
        mock_result = TelegramAuthResult(
            status="invalid_password",
            error="The password is incorrect.",
        )

        with patch("actions.telegram.TelegramClientService") as MockService:
            mock_instance = MagicMock()
            mock_instance.sign_in_with_2fa = AsyncMock(return_value=mock_result)
            MockService.return_value = mock_instance

            result = await verify_telegram_2fa({"password": "wrongpassword"})

            assert result["status"] == "invalid_password"
            assert "incorrect" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_2fa_missing_password(self) -> None:
        """Returns error when password is missing."""
        result = await verify_telegram_2fa({})

        assert result["status"] == "error"
        assert "password is required" in result["error"]

    @pytest.mark.asyncio
    async def test_2fa_error(self) -> None:
        """Returns error status on failure."""
        mock_result = TelegramAuthResult(
            status="error",
            error="Connection timeout",
        )

        with patch("actions.telegram.TelegramClientService") as MockService:
            mock_instance = MagicMock()
            mock_instance.sign_in_with_2fa = AsyncMock(return_value=mock_result)
            MockService.return_value = mock_instance

            result = await verify_telegram_2fa({"password": "test"})

            assert result["status"] == "error"
            assert "Connection timeout" in result["error"]
