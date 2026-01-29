"""
Unit tests for TelegramNamespace in meta/api.py.

These tests verify that the namespace methods correctly wrap the underlying
async action handlers with synchronous calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from meta.api import TelegramNamespace, FrankAPI


class TestTelegramNamespaceSend:
    """Tests for TelegramNamespace.send()."""

    def test_send_to_username(self) -> None:
        """Send method works with username."""
        mock_result = {
            "message": "Message sent to @johndoe",
            "success": True,
            "recipient": "@johndoe",
            "message_id": 12345,
            "text_preview": "Hello from FrankAPI!",
        }

        with patch(
            "actions.telegram.send_telegram_message", new_callable=AsyncMock
        ) as mock_action:
            mock_action.return_value = mock_result

            namespace = TelegramNamespace()
            result = namespace.send("@johndoe", "Hello from FrankAPI!")

            mock_action.assert_called_once()
            call_args = mock_action.call_args[0][0]
            assert call_args["recipient"] == "@johndoe"
            assert call_args["text"] == "Hello from FrankAPI!"

            assert result == mock_result
            assert result["success"] is True

    def test_send_to_phone_number(self) -> None:
        """Send method works with phone number."""
        mock_result = {
            "message": "Message sent to +15551234567",
            "success": True,
            "recipient": "+15551234567",
            "message_id": 12346,
            "text_preview": "Direct message.",
        }

        with patch(
            "actions.telegram.send_telegram_message", new_callable=AsyncMock
        ) as mock_action:
            mock_action.return_value = mock_result

            namespace = TelegramNamespace()
            result = namespace.send("+15551234567", "Direct message.")

            call_args = mock_action.call_args[0][0]
            assert call_args["recipient"] == "+15551234567"
            assert call_args["text"] == "Direct message."
            assert result == mock_result


class TestTelegramNamespaceMessages:
    """Tests for TelegramNamespace.messages()."""

    def test_get_messages_with_default_limit(self) -> None:
        """Messages method retrieves messages with default limit."""
        mock_result = {
            "success": True,
            "chat": "@johndoe",
            "count": 2,
            "messages": [
                {
                    "id": 100,
                    "text": "Hello",
                    "date": "2024-01-15T10:30:00+00:00",
                    "sender_id": 123,
                    "sender_name": "John Doe",
                    "is_outgoing": False,
                },
                {
                    "id": 101,
                    "text": "Hi there!",
                    "date": "2024-01-15T10:31:00+00:00",
                    "sender_id": 456,
                    "sender_name": "Me",
                    "is_outgoing": True,
                },
            ],
        }

        with patch(
            "actions.telegram.get_telegram_messages", new_callable=AsyncMock
        ) as mock_action:
            mock_action.return_value = mock_result

            namespace = TelegramNamespace()
            result = namespace.messages("@johndoe")

            mock_action.assert_called_once()
            call_args = mock_action.call_args[0][0]
            assert call_args["chat"] == "@johndoe"
            assert call_args["limit"] == 20  # default

            assert result == mock_result
            assert result["count"] == 2

    def test_get_messages_with_custom_limit(self) -> None:
        """Messages method respects custom limit."""
        mock_result = {
            "success": True,
            "chat": "group_chat",
            "count": 50,
            "messages": [],
        }

        with patch(
            "actions.telegram.get_telegram_messages", new_callable=AsyncMock
        ) as mock_action:
            mock_action.return_value = mock_result

            namespace = TelegramNamespace()
            result = namespace.messages("group_chat", limit=50)

            call_args = mock_action.call_args[0][0]
            assert call_args["chat"] == "group_chat"
            assert call_args["limit"] == 50


class TestTelegramNamespaceChats:
    """Tests for TelegramNamespace.chats()."""

    def test_list_chats_with_default_limit(self) -> None:
        """Chats method lists conversations with default limit."""
        mock_result = {
            "success": True,
            "count": 2,
            "chats": [
                {
                    "id": 1,
                    "name": "John Doe",
                    "type": "user",
                    "unread_count": 5,
                    "last_message_date": "2024-01-15T10:30:00+00:00",
                },
                {
                    "id": 2,
                    "name": "Family Group",
                    "type": "group",
                    "unread_count": 0,
                    "last_message_date": "2024-01-14T20:00:00+00:00",
                },
            ],
        }

        with patch(
            "actions.telegram.list_telegram_chats", new_callable=AsyncMock
        ) as mock_action:
            mock_action.return_value = mock_result

            namespace = TelegramNamespace()
            result = namespace.chats()

            mock_action.assert_called_once()
            call_args = mock_action.call_args[0][0]
            assert call_args["limit"] == 20  # default

            assert result == mock_result
            assert result["count"] == 2

    def test_list_chats_with_custom_limit(self) -> None:
        """Chats method respects custom limit."""
        mock_result = {
            "success": True,
            "count": 100,
            "chats": [],
        }

        with patch(
            "actions.telegram.list_telegram_chats", new_callable=AsyncMock
        ) as mock_action:
            mock_action.return_value = mock_result

            namespace = TelegramNamespace()
            result = namespace.chats(limit=100)

            call_args = mock_action.call_args[0][0]
            assert call_args["limit"] == 100


class TestFrankAPITelegramIntegration:
    """Tests for FrankAPI.telegram namespace access."""

    def test_frank_api_has_telegram_namespace(self) -> None:
        """FrankAPI provides access to TelegramNamespace via property."""
        api = FrankAPI()
        assert hasattr(api, "telegram")
        assert isinstance(api.telegram, TelegramNamespace)

    def test_frank_api_telegram_is_same_instance(self) -> None:
        """FrankAPI returns the same TelegramNamespace instance."""
        api = FrankAPI()
        assert api.telegram is api.telegram

    def test_frank_api_telegram_send_works(self) -> None:
        """FrankAPI.telegram.send() works correctly."""
        mock_result = {
            "message": "Message sent",
            "success": True,
            "recipient": "Bob",
            "message_id": 999,
            "text_preview": "Test",
        }

        with patch(
            "actions.telegram.send_telegram_message", new_callable=AsyncMock
        ) as mock_action:
            mock_action.return_value = mock_result

            api = FrankAPI()
            result = api.telegram.send("Bob", "Test")

            assert result == mock_result
            mock_action.assert_called_once()

    def test_frank_api_telegram_messages_works(self) -> None:
        """FrankAPI.telegram.messages() works correctly."""
        mock_result = {
            "success": True,
            "chat": "Bob",
            "count": 0,
            "messages": [],
        }

        with patch(
            "actions.telegram.get_telegram_messages", new_callable=AsyncMock
        ) as mock_action:
            mock_action.return_value = mock_result

            api = FrankAPI()
            result = api.telegram.messages("Bob", limit=10)

            assert result == mock_result
            mock_action.assert_called_once()

    def test_frank_api_telegram_chats_works(self) -> None:
        """FrankAPI.telegram.chats() works correctly."""
        mock_result = {
            "success": True,
            "count": 0,
            "chats": [],
        }

        with patch(
            "actions.telegram.list_telegram_chats", new_callable=AsyncMock
        ) as mock_action:
            mock_action.return_value = mock_result

            api = FrankAPI()
            result = api.telegram.chats(limit=5)

            assert result == mock_result
            mock_action.assert_called_once()
