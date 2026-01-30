"""Unit tests for Telegram jorb router."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.telegram_jorb_router import (
    _handle_telegram_message,
    _is_jorb_contact,
    _get_message_buffer,
    initialize_telegram_jorb_router,
    shutdown_telegram_jorb_router,
    get_router_status,
)


@pytest.mark.asyncio
class TestIsJorbContact:
    """Tests for _is_jorb_contact function."""

    async def test_username_match(self):
        """Returns True if username matches a jorb contact."""
        from services.jorb_storage import JorbContact

        with patch("services.telegram_jorb_router.JorbStorage") as mock_storage_cls:
            mock_storage = MagicMock()
            mock_jorb = MagicMock()
            mock_jorb.contacts = [
                JorbContact(identifier="johndoe", channel="telegram", name="John Doe"),
            ]
            mock_storage.list_jorbs = AsyncMock(return_value=[mock_jorb])
            mock_storage_cls.return_value = mock_storage

            result = await _is_jorb_contact("johndoe", "John Doe")
            assert result is True

    async def test_username_case_insensitive(self):
        """Username matching is case-insensitive."""
        from services.jorb_storage import JorbContact

        with patch("services.telegram_jorb_router.JorbStorage") as mock_storage_cls:
            mock_storage = MagicMock()
            mock_jorb = MagicMock()
            mock_jorb.contacts = [
                JorbContact(identifier="JohnDoe", channel="telegram", name="John Doe"),
            ]
            mock_storage.list_jorbs = AsyncMock(return_value=[mock_jorb])
            mock_storage_cls.return_value = mock_storage

            result = await _is_jorb_contact("johndoe", "John Doe")
            assert result is True

    async def test_name_match_when_no_username(self):
        """Falls back to name matching if username not provided."""
        from services.jorb_storage import JorbContact

        with patch("services.telegram_jorb_router.JorbStorage") as mock_storage_cls:
            mock_storage = MagicMock()
            mock_jorb = MagicMock()
            mock_jorb.contacts = [
                JorbContact(identifier="someuser", channel="telegram", name="John Doe"),
            ]
            mock_storage.list_jorbs = AsyncMock(return_value=[mock_jorb])
            mock_storage_cls.return_value = mock_storage

            # No username provided, but name matches
            result = await _is_jorb_contact(None, "John Doe")
            assert result is True

    async def test_not_in_any_jorb(self):
        """Returns False if user not in any jorb."""
        from services.jorb_storage import JorbContact

        with patch("services.telegram_jorb_router.JorbStorage") as mock_storage_cls:
            mock_storage = MagicMock()
            mock_jorb = MagicMock()
            mock_jorb.contacts = [
                JorbContact(identifier="otheruser", channel="telegram", name="Other Person"),
            ]
            mock_storage.list_jorbs = AsyncMock(return_value=[mock_jorb])
            mock_storage_cls.return_value = mock_storage

            result = await _is_jorb_contact("johndoe", "John Doe")
            assert result is False

    async def test_only_checks_telegram_channel(self):
        """Only matches contacts with telegram channel."""
        from services.jorb_storage import JorbContact

        with patch("services.telegram_jorb_router.JorbStorage") as mock_storage_cls:
            mock_storage = MagicMock()
            mock_jorb = MagicMock()
            # Same identifier but SMS channel
            mock_jorb.contacts = [
                JorbContact(identifier="johndoe", channel="sms", name="John Doe"),
            ]
            mock_storage.list_jorbs = AsyncMock(return_value=[mock_jorb])
            mock_storage_cls.return_value = mock_storage

            result = await _is_jorb_contact("johndoe", "John Doe")
            assert result is False

    async def test_no_open_jorbs(self):
        """Returns False if no open jorbs exist."""
        with patch("services.telegram_jorb_router.JorbStorage") as mock_storage_cls:
            mock_storage = MagicMock()
            mock_storage.list_jorbs = AsyncMock(return_value=[])
            mock_storage_cls.return_value = mock_storage

            result = await _is_jorb_contact("johndoe", "John Doe")
            assert result is False


@pytest.mark.asyncio
class TestHandleTelegramMessage:
    """Tests for _handle_telegram_message function."""

    def _make_mock_event(
        self,
        username: str | None = "testuser",
        first_name: str = "Test",
        last_name: str | None = "User",
        user_id: int = 12345,
        text: str = "Hello",
        is_mutual: bool = True,
    ):
        """Create a mock Telethon NewMessage.Event."""
        from telethon.tl.types import User

        event = MagicMock()

        # Mock sender using spec to ensure isinstance checks work
        sender = MagicMock(spec=User)
        sender.username = username
        sender.first_name = first_name
        sender.last_name = last_name
        sender.id = user_id
        sender.mutual_contact = is_mutual

        # Make get_sender return the user
        event.get_sender = AsyncMock(return_value=sender)

        # Mock message
        event.message = MagicMock()
        event.message.text = text
        event.message.date = datetime(2026, 1, 30, 12, 0, 0, tzinfo=timezone.utc)

        return event

    async def test_buffers_message_from_jorb_contact(self):
        """Messages from jorb contacts are buffered."""
        event = self._make_mock_event()

        with patch("services.telegram_jorb_router._is_jorb_contact", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = True

            with patch("services.telegram_jorb_router._get_message_buffer") as mock_buffer_fn:
                mock_buffer = MagicMock()
                mock_buffer.buffer_message = AsyncMock(return_value=True)
                mock_buffer_fn.return_value = mock_buffer

                await _handle_telegram_message(event)

                mock_buffer.buffer_message.assert_called_once()
                call_kwargs = mock_buffer.buffer_message.call_args.kwargs
                assert call_kwargs["channel"] == "telegram"
                assert call_kwargs["sender"] == "@testuser"
                assert call_kwargs["sender_name"] == "Test User"
                assert call_kwargs["content"] == "Hello"

    async def test_skips_non_jorb_contacts(self):
        """Messages from non-jorb contacts are skipped."""
        event = self._make_mock_event()

        with patch("services.telegram_jorb_router._is_jorb_contact", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = False

            with patch("services.telegram_jorb_router._get_message_buffer") as mock_buffer_fn:
                mock_buffer = MagicMock()
                mock_buffer.buffer_message = AsyncMock()
                mock_buffer_fn.return_value = mock_buffer

                await _handle_telegram_message(event)

                # Buffer should NOT be called
                mock_buffer.buffer_message.assert_not_called()

    async def test_uses_user_id_when_no_username(self):
        """Falls back to user ID when no username available."""
        event = self._make_mock_event(username=None, user_id=98765)

        with patch("services.telegram_jorb_router._is_jorb_contact", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = True

            with patch("services.telegram_jorb_router._get_message_buffer") as mock_buffer_fn:
                mock_buffer = MagicMock()
                mock_buffer.buffer_message = AsyncMock(return_value=True)
                mock_buffer_fn.return_value = mock_buffer

                await _handle_telegram_message(event)

                call_kwargs = mock_buffer.buffer_message.call_args.kwargs
                assert call_kwargs["sender"] == "98765"

    async def test_skips_empty_text(self):
        """Messages with no text are skipped."""
        event = self._make_mock_event(text="")

        with patch("services.telegram_jorb_router._is_jorb_contact", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = True

            with patch("services.telegram_jorb_router._get_message_buffer") as mock_buffer_fn:
                mock_buffer = MagicMock()
                mock_buffer.buffer_message = AsyncMock()
                mock_buffer_fn.return_value = mock_buffer

                await _handle_telegram_message(event)

                mock_buffer.buffer_message.assert_not_called()

    async def test_skips_no_sender(self):
        """Messages with no sender are skipped."""
        event = MagicMock()
        event.get_sender = AsyncMock(return_value=None)

        with patch("services.telegram_jorb_router._get_message_buffer") as mock_buffer_fn:
            mock_buffer = MagicMock()
            mock_buffer.buffer_message = AsyncMock()
            mock_buffer_fn.return_value = mock_buffer

            await _handle_telegram_message(event)

            mock_buffer.buffer_message.assert_not_called()


@pytest.mark.asyncio
class TestRouterInitialization:
    """Tests for router initialization and shutdown."""

    async def test_initialize_success(self):
        """Successful initialization returns True."""
        with patch("services.telegram_jorb_router.TelegramClientService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service.is_configured = True
            mock_service.connect = AsyncMock()
            mock_service.register_message_handler = MagicMock()
            mock_service.start_listening = AsyncMock()
            mock_service_cls.return_value = mock_service

            # Reset global state
            import services.telegram_jorb_router as router
            router._is_initialized = False
            router._telegram_service = None

            result = await initialize_telegram_jorb_router()
            assert result is True

            mock_service.connect.assert_called_once()
            mock_service.register_message_handler.assert_called_once()
            mock_service.start_listening.assert_called_once()

    async def test_initialize_not_configured(self):
        """Returns False if Telegram not configured."""
        with patch("services.telegram_jorb_router.TelegramClientService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service.is_configured = False
            mock_service_cls.return_value = mock_service

            # Reset global state
            import services.telegram_jorb_router as router
            router._is_initialized = False
            router._telegram_service = None

            result = await initialize_telegram_jorb_router()
            assert result is False

    async def test_shutdown_flushes_pending(self):
        """Shutdown flushes pending messages."""
        # Setup mock services
        import services.telegram_jorb_router as router

        mock_telegram = MagicMock()
        mock_telegram.stop_listening = AsyncMock()
        mock_telegram.unregister_message_handler = MagicMock()

        mock_buffer = MagicMock()
        mock_buffer.flush_all = AsyncMock(return_value=[])

        router._telegram_service = mock_telegram
        router._message_buffer = mock_buffer
        router._is_initialized = True

        await shutdown_telegram_jorb_router()

        mock_telegram.stop_listening.assert_called_once()
        mock_buffer.flush_all.assert_called_once()
        assert router._is_initialized is False


class TestRouterStatus:
    """Tests for get_router_status function."""

    def test_status_when_not_initialized(self):
        """Returns correct status when not initialized."""
        import services.telegram_jorb_router as router

        router._is_initialized = False
        router._telegram_service = None
        router._agent_runner = None
        router._message_buffer = None

        status = get_router_status()

        assert status["initialized"] is False
        assert status["telegram_configured"] is False
        assert status["agent_configured"] is False
        assert status["pending_messages"] == 0

    def test_status_when_initialized(self):
        """Returns correct status when initialized."""
        import services.telegram_jorb_router as router

        mock_telegram = MagicMock()
        mock_telegram.is_configured = True

        mock_agent = MagicMock()
        mock_agent.is_configured = True

        router._is_initialized = True
        router._telegram_service = mock_telegram
        router._agent_runner = mock_agent
        router._message_buffer = None

        status = get_router_status()

        assert status["initialized"] is True
        assert status["telegram_configured"] is True
        assert status["agent_configured"] is True
