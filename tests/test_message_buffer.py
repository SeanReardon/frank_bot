"""
Unit tests for MessageBuffer service.
"""

import asyncio
from datetime import datetime, timezone

import pytest

from services.message_buffer import (
    BufferedEvent,
    MessageBuffer,
)


@pytest.fixture
def buffer():
    """Create a MessageBuffer instance with short debounce times for testing."""
    return MessageBuffer(
        debounce_telegram_seconds=1,
        debounce_sms_seconds=1,
    )


class TestMessageBuffering:
    """Tests for message buffering behavior."""

    async def test_buffer_first_message_returns_true(self, buffer):
        """First message in a window returns True."""
        result = await buffer.buffer_message(
            channel="telegram",
            sender="@user",
            content="Hello",
        )
        assert result is True

    async def test_buffer_subsequent_message_returns_false(self, buffer):
        """Subsequent messages in same window return False."""
        await buffer.buffer_message(
            channel="telegram",
            sender="@user",
            content="Hello",
        )
        result = await buffer.buffer_message(
            channel="telegram",
            sender="@user",
            content="World",
        )
        assert result is False

    async def test_different_senders_are_separate(self, buffer):
        """Different senders have separate buffers."""
        result1 = await buffer.buffer_message(
            channel="telegram",
            sender="@user1",
            content="Message 1",
        )
        result2 = await buffer.buffer_message(
            channel="telegram",
            sender="@user2",
            content="Message 2",
        )
        assert result1 is True
        assert result2 is True

    async def test_different_channels_are_separate(self, buffer):
        """Same sender on different channels have separate buffers."""
        result1 = await buffer.buffer_message(
            channel="telegram",
            sender="+15551234567",
            content="Telegram message",
        )
        result2 = await buffer.buffer_message(
            channel="sms",
            sender="+15551234567",
            content="SMS message",
        )
        assert result1 is True
        assert result2 is True

    async def test_has_pending_messages(self, buffer):
        """has_pending_messages returns correct state."""
        assert buffer.has_pending_messages("@user", "telegram") is False

        await buffer.buffer_message(
            channel="telegram",
            sender="@user",
            content="Hello",
        )

        assert buffer.has_pending_messages("@user", "telegram") is True
        assert buffer.has_pending_messages("@other", "telegram") is False

    async def test_get_pending_count(self, buffer):
        """get_pending_count returns correct count."""
        assert buffer.get_pending_count("@user", "telegram") == 0

        await buffer.buffer_message(
            channel="telegram",
            sender="@user",
            content="Message 1",
        )
        assert buffer.get_pending_count("@user", "telegram") == 1

        await buffer.buffer_message(
            channel="telegram",
            sender="@user",
            content="Message 2",
        )
        assert buffer.get_pending_count("@user", "telegram") == 2


class TestMessageFlushing:
    """Tests for buffer flushing behavior."""

    async def test_flush_buffer_combines_messages(self, buffer):
        """flush_buffer combines messages with newlines."""
        await buffer.buffer_message(
            channel="telegram",
            sender="@user",
            content="Hello",
        )
        await buffer.buffer_message(
            channel="telegram",
            sender="@user",
            content="How are you?",
        )
        await buffer.buffer_message(
            channel="telegram",
            sender="@user",
            content="Let me know!",
        )

        event = await buffer.flush_buffer("@user", "telegram")

        assert event is not None
        assert event.channel == "telegram"
        assert event.sender == "@user"
        assert event.content == "Hello\nHow are you?\nLet me know!"
        assert event.message_count == 3

    async def test_flush_buffer_returns_none_when_empty(self, buffer):
        """flush_buffer returns None for non-existent buffer."""
        event = await buffer.flush_buffer("@nonexistent", "telegram")
        assert event is None

    async def test_flush_buffer_clears_buffer(self, buffer):
        """flush_buffer removes the buffer after flushing."""
        await buffer.buffer_message(
            channel="telegram",
            sender="@user",
            content="Hello",
        )

        await buffer.flush_buffer("@user", "telegram")

        assert buffer.has_pending_messages("@user", "telegram") is False
        assert buffer.get_pending_count("@user", "telegram") == 0

    async def test_flush_buffer_preserves_sender_name(self, buffer):
        """flush_buffer preserves sender_name from first message."""
        await buffer.buffer_message(
            channel="sms",
            sender="+15551234567",
            sender_name="John Doe",
            content="Hi there",
        )

        event = await buffer.flush_buffer("+15551234567", "sms")

        assert event is not None
        assert event.sender_name == "John Doe"

    async def test_flush_all(self, buffer):
        """flush_all flushes all pending buffers."""
        await buffer.buffer_message(
            channel="telegram",
            sender="@user1",
            content="Message 1",
        )
        await buffer.buffer_message(
            channel="sms",
            sender="+15551234567",
            content="Message 2",
        )

        events = await buffer.flush_all()

        assert len(events) == 2
        assert buffer.has_pending_messages("@user1", "telegram") is False
        assert buffer.has_pending_messages("+15551234567", "sms") is False


class TestDebounceTimer:
    """Tests for debounce timer behavior."""

    async def test_auto_flush_after_debounce(self, buffer):
        """Buffer automatically flushes after debounce period."""
        flushed_events: list[BufferedEvent] = []

        async def on_flush(event: BufferedEvent) -> None:
            flushed_events.append(event)

        buffer.set_flush_callback(on_flush)

        await buffer.buffer_message(
            channel="telegram",
            sender="@user",
            content="Auto flush message",
        )

        # Wait for debounce (1 second + small buffer)
        await asyncio.sleep(1.2)

        assert len(flushed_events) == 1
        assert flushed_events[0].content == "Auto flush message"
        assert buffer.has_pending_messages("@user", "telegram") is False

    async def test_messages_combined_within_debounce_window(self, buffer):
        """Messages sent within debounce window are combined."""
        flushed_events: list[BufferedEvent] = []

        async def on_flush(event: BufferedEvent) -> None:
            flushed_events.append(event)

        buffer.set_flush_callback(on_flush)

        await buffer.buffer_message(
            channel="telegram",
            sender="@user",
            content="First",
        )
        await asyncio.sleep(0.3)
        await buffer.buffer_message(
            channel="telegram",
            sender="@user",
            content="Second",
        )
        await asyncio.sleep(0.3)
        await buffer.buffer_message(
            channel="telegram",
            sender="@user",
            content="Third",
        )

        # Wait for debounce from first message
        await asyncio.sleep(0.6)

        assert len(flushed_events) == 1
        assert flushed_events[0].content == "First\nSecond\nThird"
        assert flushed_events[0].message_count == 3

    async def test_manual_flush_cancels_timer(self, buffer):
        """Manual flush cancels the auto-flush timer."""
        flushed_events: list[BufferedEvent] = []

        async def on_flush(event: BufferedEvent) -> None:
            flushed_events.append(event)

        buffer.set_flush_callback(on_flush)

        await buffer.buffer_message(
            channel="telegram",
            sender="@user",
            content="Message",
        )

        # Manually flush before timer fires
        await buffer.flush_buffer("@user", "telegram")

        # Callback is called on manual flush
        assert len(flushed_events) == 1

        # Wait past the original debounce time
        await asyncio.sleep(1.2)

        # No additional flushes
        assert len(flushed_events) == 1


class TestDebounceConfiguration:
    """Tests for debounce time configuration."""

    def test_default_debounce_times(self):
        """Default debounce times are set correctly."""
        buffer = MessageBuffer()
        assert buffer.get_debounce_time("telegram") == 60
        assert buffer.get_debounce_time("sms") == 30

    def test_custom_debounce_times(self):
        """Custom debounce times are respected."""
        buffer = MessageBuffer(
            debounce_telegram_seconds=120,
            debounce_sms_seconds=15,
        )
        assert buffer.get_debounce_time("telegram") == 120
        assert buffer.get_debounce_time("sms") == 15


class TestClear:
    """Tests for clear functionality."""

    async def test_clear_removes_all_buffers(self, buffer):
        """clear removes all buffers without flushing."""
        await buffer.buffer_message(
            channel="telegram",
            sender="@user1",
            content="Message 1",
        )
        await buffer.buffer_message(
            channel="sms",
            sender="+15551234567",
            content="Message 2",
        )

        buffer.clear()

        assert buffer.has_pending_messages("@user1", "telegram") is False
        assert buffer.has_pending_messages("+15551234567", "sms") is False
