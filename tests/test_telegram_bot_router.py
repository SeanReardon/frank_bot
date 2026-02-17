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

    @pytest.mark.asyncio
    async def test_android_screen_natural_language_bypasses_buffer(self):
        """Natural language screenshot requests should also bypass the LLM path."""
        with patch(
            "services.telegram_bot_router._send_android_screen_via_bot",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_send, patch(
            "services.telegram_bot_router._get_message_buffer"
        ) as mock_get_buffer:
            mock_buffer = MagicMock()
            mock_buffer.buffer_message = AsyncMock()
            mock_get_buffer.return_value = mock_buffer

            from services.telegram_bot_router import _handle_bot_message

            await _handle_bot_message(
                "can you take a screenshot of my android device and send it to me?",
                "SeanReardon",
                "12345",
                "Sean Reardon",
            )

        mock_send.assert_called_once_with(chat_id="12345")
        mock_buffer.buffer_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_screen_recovers_from_blank_screenshot(self):
        """If screenshot looks blank (tiny), it retries after wake/unlock/home."""
        from services.android_client import ADBResult

        # Fake AndroidClient with two screenshots: tiny then normal.
        mock_client = MagicMock()
        mock_client.take_screenshot = AsyncMock(side_effect=[
            ADBResult(success=True, output="/tmp/blank.png"),
            ADBResult(success=True, output="/tmp/ok.png"),
        ])
        mock_client.wake_device = AsyncMock()
        mock_client.unlock_device = AsyncMock()
        mock_client.press_key = AsyncMock()

        mock_bot = MagicMock()
        mock_bot.send_notification = AsyncMock(return_value=MagicMock(success=True))
        mock_bot.send_photo = AsyncMock(return_value=MagicMock(success=True, error=None))

        with patch("services.android_client.AndroidClient", return_value=mock_client), patch(
            "services.telegram_bot.TelegramBot",
            return_value=mock_bot,
        ), patch(
            "config.get_settings",
            return_value=MagicMock(telegram_bot_token="t"),
        ), patch(
            "services.telegram_bot_router.os.path.exists",
            side_effect=lambda p: True,
        ), patch(
            "services.telegram_bot_router.os.path.getsize",
            side_effect=lambda p: 12_000 if p.endswith("blank.png") else 200_000,
        ):
            from services.telegram_bot_router import _send_android_screen_via_bot

            ok = await _send_android_screen_via_bot(chat_id="123")

        assert ok is True
        assert mock_client.take_screenshot.call_count == 2
        mock_client.wake_device.assert_called()
        mock_client.unlock_device.assert_called()
        mock_client.press_key.assert_called_with("home")
        mock_bot.send_photo.assert_called_once()

    @pytest.mark.asyncio
    async def test_screen_does_not_send_black_image(self):
        """If screenshot stays blank after recovery, it should not send a photo."""
        from services.android_client import ADBResult

        mock_client = MagicMock()
        mock_client.take_screenshot = AsyncMock(side_effect=[
            ADBResult(success=True, output="/tmp/blank1.png"),
            ADBResult(success=True, output="/tmp/blank2.png"),
        ])
        mock_client.wake_device = AsyncMock()
        mock_client.unlock_device = AsyncMock()
        mock_client.press_key = AsyncMock()
        # Used for lockscreen hint; return a non-success result to keep it simple.
        mock_client._run_adb = AsyncMock(return_value=ADBResult(success=False, output="", error="no"))

        mock_bot = MagicMock()
        mock_bot.send_notification = AsyncMock(return_value=MagicMock(success=True))
        mock_bot.send_photo = AsyncMock(return_value=MagicMock(success=True, error=None))

        with patch("services.android_client.AndroidClient", return_value=mock_client), patch(
            "services.telegram_bot.TelegramBot",
            return_value=mock_bot,
        ), patch(
            "config.get_settings",
            return_value=MagicMock(telegram_bot_token="t"),
        ), patch(
            "services.telegram_bot_router.os.path.exists",
            side_effect=lambda p: True,
        ), patch(
            "services.telegram_bot_router.os.path.getsize",
            side_effect=lambda p: 12_000,
        ):
            from services.telegram_bot_router import _send_android_screen_via_bot

            ok = await _send_android_screen_via_bot(chat_id="123")

        assert ok is False
        mock_bot.send_notification.assert_called()
        mock_bot.send_photo.assert_not_called()


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
