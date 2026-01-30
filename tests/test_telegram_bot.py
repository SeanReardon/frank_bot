"""Unit tests for Telegram Bot notification service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx

from services.telegram_bot import (
    NotificationResult,
    TelegramBot,
    _escape_html,
)


class TestEscapeHtml:
    """Tests for HTML escaping."""

    def test_escapes_ampersand(self):
        """Ampersand is escaped."""
        result = _escape_html("A & B")
        assert result == "A &amp; B"

    def test_escapes_less_than(self):
        """Less than is escaped."""
        result = _escape_html("1 < 2")
        assert result == "1 &lt; 2"

    def test_escapes_greater_than(self):
        """Greater than is escaped."""
        result = _escape_html("2 > 1")
        assert result == "2 &gt; 1"

    def test_escapes_all(self):
        """All special chars are escaped."""
        result = _escape_html("<tag>A & B</tag>")
        assert result == "&lt;tag&gt;A &amp; B&lt;/tag&gt;"

    def test_preserves_normal_text(self):
        """Normal text is unchanged."""
        result = _escape_html("Hello, World!")
        assert result == "Hello, World!"


class TestTelegramBotIsConfigured:
    """Tests for TelegramBot.is_configured."""

    def test_configured_with_both(self):
        """Returns True when both token and chat_id are set."""
        bot = TelegramBot(token="test-token", chat_id="12345")
        assert bot.is_configured is True

    def test_not_configured_without_token(self):
        """Returns False when token is missing."""
        bot = TelegramBot(token=None, chat_id="12345")
        assert bot.is_configured is False

    def test_not_configured_without_chat_id(self):
        """Returns False when chat_id is missing."""
        bot = TelegramBot(token="test-token", chat_id=None)
        assert bot.is_configured is False

    def test_not_configured_without_both(self):
        """Returns False when both are missing."""
        bot = TelegramBot(token=None, chat_id=None)
        assert bot.is_configured is False


class TestTelegramBotSendNotification:
    """Tests for send_notification method."""

    @pytest.mark.asyncio
    async def test_successful_send(self):
        """Notification is sent successfully."""
        bot = TelegramBot(token="test-token", chat_id="12345")

        with patch("services.telegram_bot.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "ok": True,
                "result": {"message_id": 789},
            }
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await bot.send_notification("Test message")

            assert result.success is True
            assert result.message_id == 789
            assert result.error is None

    @pytest.mark.asyncio
    async def test_send_without_token(self):
        """Error returned when token is missing."""
        bot = TelegramBot(token=None, chat_id="12345")

        result = await bot.send_notification("Test message")

        assert result.success is False
        assert "token not configured" in result.error

    @pytest.mark.asyncio
    async def test_send_without_chat_id(self):
        """Error returned when chat_id is missing."""
        bot = TelegramBot(token="test-token", chat_id=None)

        result = await bot.send_notification("Test message")

        assert result.success is False
        assert "chat_id not configured" in result.error

    @pytest.mark.asyncio
    async def test_send_with_override_chat_id(self):
        """Can override default chat_id."""
        bot = TelegramBot(token="test-token", chat_id="default-id")

        with patch("services.telegram_bot.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"ok": True, "result": {"message_id": 1}}
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            await bot.send_notification("Test", chat_id="override-id")

            # Verify the chat_id in the request
            call_kwargs = mock_post.call_args.kwargs
            assert call_kwargs["json"]["chat_id"] == "override-id"

    @pytest.mark.asyncio
    async def test_api_error_response(self):
        """Error returned for API error response."""
        bot = TelegramBot(token="test-token", chat_id="12345")

        with patch("services.telegram_bot.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "ok": False,
                "description": "Bad Request: chat not found",
            }
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await bot.send_notification("Test")

            assert result.success is False
            assert "chat not found" in result.error

    @pytest.mark.asyncio
    async def test_http_error_response(self):
        """Error returned for HTTP error."""
        bot = TelegramBot(token="test-token", chat_id="12345")

        with patch("services.telegram_bot.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 401
            mock_response.text = "Unauthorized"
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await bot.send_notification("Test")

            assert result.success is False
            assert "401" in result.error

    @pytest.mark.asyncio
    async def test_timeout_error(self):
        """Error returned on timeout."""
        bot = TelegramBot(token="test-token", chat_id="12345")

        with patch("services.telegram_bot.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=httpx.TimeoutException("Connection timeout")
            )

            result = await bot.send_notification("Test")

            assert result.success is False
            assert "timeout" in result.error.lower()


class TestTelegramBotNotifyUnknownSms:
    """Tests for notify_unknown_sms method."""

    @pytest.mark.asyncio
    async def test_formats_notification(self):
        """Notification is formatted correctly."""
        bot = TelegramBot(token="test-token", chat_id="12345")

        with patch("services.telegram_bot.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"ok": True, "result": {"message_id": 1}}
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            await bot.notify_unknown_sms(
                from_number="+15551234567",
                message="Hello there!",
                attachment_count=0,
            )

            call_kwargs = mock_post.call_args.kwargs
            text = call_kwargs["json"]["text"]

            assert "Unknown SMS Sender" in text
            assert "+15551234567" in text
            assert "Hello there!" in text

    @pytest.mark.asyncio
    async def test_shows_attachment_count(self):
        """Attachment count is shown when present."""
        bot = TelegramBot(token="test-token", chat_id="12345")

        with patch("services.telegram_bot.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"ok": True, "result": {"message_id": 1}}
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            await bot.notify_unknown_sms(
                from_number="+15551234567",
                message="Photo message",
                attachment_count=2,
            )

            call_kwargs = mock_post.call_args.kwargs
            text = call_kwargs["json"]["text"]

            assert "2 attachment(s)" in text

    @pytest.mark.asyncio
    async def test_truncates_long_message(self):
        """Long messages are truncated."""
        bot = TelegramBot(token="test-token", chat_id="12345")

        with patch("services.telegram_bot.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"ok": True, "result": {"message_id": 1}}
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            long_message = "A" * 1000

            await bot.notify_unknown_sms(
                from_number="+15551234567",
                message=long_message,
            )

            call_kwargs = mock_post.call_args.kwargs
            text = call_kwargs["json"]["text"]

            # Should have ellipsis and not full message
            assert "..." in text
            # Original message shouldn't be fully present
            assert long_message not in text

    @pytest.mark.asyncio
    async def test_escapes_html_in_message(self):
        """HTML in message is escaped."""
        bot = TelegramBot(token="test-token", chat_id="12345")

        with patch("services.telegram_bot.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"ok": True, "result": {"message_id": 1}}
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            await bot.notify_unknown_sms(
                from_number="+15551234567",
                message="<script>alert('xss')</script>",
            )

            call_kwargs = mock_post.call_args.kwargs
            text = call_kwargs["json"]["text"]

            # Should be escaped
            assert "&lt;script&gt;" in text
            assert "<script>" not in text


class TestTelegramBotNotifySpam:
    """Tests for notify_spam method."""

    @pytest.mark.asyncio
    async def test_formats_spam_notification(self):
        """Spam notification is formatted correctly."""
        bot = TelegramBot(token="test-token", chat_id="12345")

        with patch("services.telegram_bot.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"ok": True, "result": {"message_id": 1}}
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            await bot.notify_spam(
                from_number="+15551234567",
                message="Buy now!",
                reason="Marketing keywords detected",
            )

            call_kwargs = mock_post.call_args.kwargs
            text = call_kwargs["json"]["text"]

            assert "Spam SMS Detected" in text
            assert "+15551234567" in text
            assert "Buy now!" in text
            assert "Marketing keywords detected" in text


class TestNotificationResult:
    """Tests for NotificationResult dataclass."""

    def test_successful_result(self):
        """Successful result has correct fields."""
        result = NotificationResult(success=True, message_id=123)
        assert result.success is True
        assert result.message_id == 123
        assert result.error is None

    def test_failed_result(self):
        """Failed result has correct fields."""
        result = NotificationResult(success=False, error="Some error")
        assert result.success is False
        assert result.message_id is None
        assert result.error == "Some error"
