"""
Tests for the Telegram Bot Router.

Validates MessageBuffer-based debouncing, flush callback creating
IncomingEvent with channel='telegram_bot', and lifecycle functions.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.telegram_bot_router import (
    _handle_bot_message,
    _normalize_sender,
    _on_bot_message_flush,
    get_bot_router_status,
    initialize_telegram_bot_router,
    shutdown_telegram_bot_router,
)


class TestNormalizeSender:
    """Tests for sender normalization."""

    def test_username_prefixed_with_at(self):
        assert _normalize_sender("alice", None) == "@alice"

    def test_empty_username_falls_back_to_name(self):
        assert _normalize_sender("", "Bob Smith") == "Bob Smith"

    def test_no_username_no_name_returns_unknown(self):
        assert _normalize_sender("", None) == "unknown"

    def test_whitespace_username_falls_back(self):
        assert _normalize_sender("  ", "Carol") == "Carol"


class TestFlushCallback:
    """Tests for _on_bot_message_flush creating correct IncomingEvent."""

    @pytest.mark.asyncio
    async def test_creates_incoming_event_with_telegram_bot_channel(self):
        """Flush callback creates IncomingEvent with channel='telegram_bot'."""
        from services.message_buffer import BufferedEvent

        event = BufferedEvent(
            channel="telegram_bot",
            sender="@alice",
            sender_name="Alice",
            content="Hello from bot",
            timestamp="2026-02-13T10:00:00+00:00",
            message_count=1,
            metadata={"telegram_bot_chat_id": "12345"},
        )

        mock_runner = MagicMock()
        mock_runner.is_configured = True
        mock_runner.process_incoming_message = AsyncMock(
            return_value=MagicMock(jorb_id="jorb_1", action_taken="matched", success=True)
        )

        with patch(
            "services.telegram_bot_router._agent_runner",
            mock_runner,
        ):
            await _on_bot_message_flush(event)

        mock_runner.process_incoming_message.assert_called_once()
        incoming = mock_runner.process_incoming_message.call_args[0][0]

        assert incoming.channel == "telegram_bot"
        assert incoming.sender == "@alice"
        assert incoming.sender_name == "Alice"
        assert incoming.content == "Hello from bot"
        assert incoming.metadata["source"] == "telegram_bot"
        assert incoming.metadata["telegram_bot_chat_id"] == "12345"
        assert incoming.message_count == 1

    @pytest.mark.asyncio
    async def test_flush_skips_when_runner_not_configured(self, caplog):
        """Flush callback skips processing when AgentRunner is not configured."""
        from services.message_buffer import BufferedEvent

        event = BufferedEvent(
            channel="telegram_bot",
            sender="@alice",
            sender_name="Alice",
            content="Hello",
            timestamp="2026-02-13T10:00:00+00:00",
            message_count=1,
        )

        mock_runner = MagicMock()
        mock_runner.is_configured = False

        with patch("services.telegram_bot_router._agent_runner", mock_runner):
            await _on_bot_message_flush(event)

        mock_runner.process_incoming_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_flush_creates_runner_if_none(self):
        """Flush callback creates AgentRunner if module-level instance is None."""
        from services.message_buffer import BufferedEvent

        event = BufferedEvent(
            channel="telegram_bot",
            sender="@alice",
            sender_name="Alice",
            content="Hello",
            timestamp="2026-02-13T10:00:00+00:00",
            message_count=1,
        )

        mock_runner_cls = MagicMock()
        mock_runner_instance = MagicMock()
        mock_runner_instance.is_configured = True
        mock_runner_instance.process_incoming_message = AsyncMock(
            return_value=MagicMock(jorb_id=None, action_taken="no_match", success=True)
        )
        mock_runner_cls.return_value = mock_runner_instance

        import services.telegram_bot_router as mod
        original = mod._agent_runner
        mod._agent_runner = None

        try:
            with patch("services.telegram_bot_router.AgentRunner", mock_runner_cls):
                await _on_bot_message_flush(event)

            mock_runner_cls.assert_called_once()
        finally:
            mod._agent_runner = original

    @pytest.mark.asyncio
    async def test_flush_handles_processing_error(self, caplog):
        """Flush callback handles errors from AgentRunner gracefully."""
        from services.message_buffer import BufferedEvent

        event = BufferedEvent(
            channel="telegram_bot",
            sender="@alice",
            sender_name="Alice",
            content="Hello",
            timestamp="2026-02-13T10:00:00+00:00",
            message_count=1,
        )

        mock_runner = MagicMock()
        mock_runner.is_configured = True
        mock_runner.process_incoming_message = AsyncMock(
            side_effect=RuntimeError("LLM down")
        )

        with patch("services.telegram_bot_router._agent_runner", mock_runner):
            # Should not raise
            await _on_bot_message_flush(event)

        assert "Error processing bot message" in caplog.text


class TestHandleBotMessage:
    """Tests for _handle_bot_message buffering."""

    @pytest.mark.asyncio
    async def test_buffers_message_with_telegram_bot_channel(self):
        """Messages are buffered with channel='telegram_bot' and metadata."""
        mock_buffer = MagicMock()
        mock_buffer.buffer_message = AsyncMock(return_value=True)

        with patch(
            "services.telegram_bot_router._get_message_buffer",
            return_value=mock_buffer,
        ):
            await _handle_bot_message("Hello", "alice", "12345", "Alice")

        mock_buffer.buffer_message.assert_called_once()
        call_kwargs = mock_buffer.buffer_message.call_args[1]

        assert call_kwargs["channel"] == "telegram_bot"
        assert call_kwargs["sender"] == "@alice"
        assert call_kwargs["content"] == "Hello"
        assert call_kwargs["sender_name"] == "Alice"
        assert call_kwargs["metadata"] == {"telegram_bot_chat_id": "12345"}

    @pytest.mark.asyncio
    async def test_buffers_message_without_username(self):
        """Messages without username use sender_name as fallback."""
        mock_buffer = MagicMock()
        mock_buffer.buffer_message = AsyncMock(return_value=True)

        with patch(
            "services.telegram_bot_router._get_message_buffer",
            return_value=mock_buffer,
        ):
            await _handle_bot_message("Hello", "", "99999", "Bob Smith")

        call_kwargs = mock_buffer.buffer_message.call_args[1]
        assert call_kwargs["sender"] == "Bob Smith"

    @pytest.mark.asyncio
    async def test_android_screen_command_bypasses_buffer(self):
        """Android screen command is handled directly (no LLM, no buffering)."""
        mock_buffer = MagicMock()
        mock_buffer.buffer_message = AsyncMock(return_value=True)

        mock_send = AsyncMock(return_value=True)

        with patch(
            "services.telegram_bot_router._send_android_screen_via_bot",
            mock_send,
        ), patch(
            "services.telegram_bot_router._get_message_buffer",
            return_value=mock_buffer,
        ):
            await _handle_bot_message(
                "show me the android screen",
                "alice",
                "12345",
                "Alice",
            )

        mock_send.assert_called_once_with(chat_id="12345")
        mock_buffer.buffer_message.assert_not_called()


class TestLifecycle:
    """Tests for initialization and shutdown."""

    @pytest.mark.asyncio
    async def test_initialize_starts_polling(self):
        """initialize_telegram_bot_router starts the listener polling."""
        mock_listener = MagicMock()
        mock_listener.is_configured = True
        mock_listener.start_polling = AsyncMock()

        with patch(
            "services.telegram_bot_router.TelegramBotListener",
            return_value=mock_listener,
        ):
            import services.telegram_bot_router as mod
            mod._is_initialized = False
            mod._listener = None

            result = await initialize_telegram_bot_router()

            assert result is True
            mock_listener.start_polling.assert_called_once()

            # Clean up
            mod._is_initialized = False
            mod._listener = None

    @pytest.mark.asyncio
    async def test_initialize_returns_false_when_not_configured(self):
        """initialize_telegram_bot_router returns False when bot not configured."""
        mock_listener = MagicMock()
        mock_listener.is_configured = False

        with patch(
            "services.telegram_bot_router.TelegramBotListener",
            return_value=mock_listener,
        ):
            import services.telegram_bot_router as mod
            mod._is_initialized = False
            mod._listener = None

            result = await initialize_telegram_bot_router()

            assert result is False

    @pytest.mark.asyncio
    async def test_shutdown_stops_polling_and_flushes(self):
        """shutdown_telegram_bot_router stops polling and flushes buffer."""
        mock_listener = MagicMock()
        mock_listener.stop_polling = AsyncMock()

        mock_buffer = MagicMock()
        mock_buffer.flush_all = AsyncMock(return_value=[])

        import services.telegram_bot_router as mod
        mod._is_initialized = True
        mod._listener = mock_listener
        mod._message_buffer = mock_buffer

        await shutdown_telegram_bot_router()

        mock_listener.stop_polling.assert_called_once()
        mock_buffer.flush_all.assert_called_once()
        assert not mod._is_initialized

    def test_get_status_returns_expected_keys(self):
        """get_bot_router_status returns dict with required keys."""
        import services.telegram_bot_router as mod
        mod._is_initialized = False
        mod._listener = None
        mod._message_buffer = None
        mod._last_error = None

        status = get_bot_router_status()

        assert "initialized" in status
        assert "listener_configured" in status
        assert "listener_running" in status
        assert "pending_messages" in status
        assert "last_error" in status
        assert status["initialized"] is False
        assert status["pending_messages"] == 0
