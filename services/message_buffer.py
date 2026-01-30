"""
Message Buffer Service for debouncing incoming messages.

Collects messages from the same sender/channel and combines them
after a configurable debounce window expires.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Literal

logger = logging.getLogger(__name__)

# Default debounce times (in seconds)
DEFAULT_DEBOUNCE_TELEGRAM = 60
DEFAULT_DEBOUNCE_SMS = 30

Channel = Literal["telegram", "sms", "email"]


@dataclass
class BufferedMessage:
    """A single buffered message."""

    channel: Channel
    sender: str
    sender_name: str | None
    content: str
    timestamp: str  # ISO 8601


@dataclass
class BufferedEvent:
    """Combined event from multiple buffered messages."""

    channel: Channel
    sender: str
    sender_name: str | None
    content: str  # Combined content with newlines
    timestamp: str  # Timestamp of first message
    message_count: int  # Number of messages combined


@dataclass
class BufferEntry:
    """Internal buffer entry tracking messages and timer."""

    messages: list[BufferedMessage] = field(default_factory=list)
    timer_task: asyncio.Task[None] | None = None
    first_message_time: str | None = None


def _get_buffer_key(sender: str, channel: Channel) -> str:
    """Generate a unique key for sender/channel combination."""
    return f"{channel}:{sender}"


class MessageBuffer:
    """
    Service for debouncing incoming messages.

    Messages from the same sender/channel within a configurable window
    are combined into a single event before processing.
    """

    def __init__(
        self,
        on_flush: Callable[[BufferedEvent], Coroutine[Any, Any, None]] | None = None,
        debounce_telegram_seconds: int | None = None,
        debounce_sms_seconds: int | None = None,
    ):
        """
        Initialize the message buffer.

        Args:
            on_flush: Async callback called when buffer is flushed
            debounce_telegram_seconds: Debounce window for Telegram (default: DEBOUNCE_TELEGRAM_SECONDS env or 60)
            debounce_sms_seconds: Debounce window for SMS (default: DEBOUNCE_SMS_SECONDS env or 30)
        """
        self._on_flush = on_flush
        self._buffers: dict[str, BufferEntry] = {}

        # Get debounce times from env or use provided values
        self._debounce_times: dict[Channel, int] = {
            "telegram": debounce_telegram_seconds or int(
                os.getenv("DEBOUNCE_TELEGRAM_SECONDS", str(DEFAULT_DEBOUNCE_TELEGRAM))
            ),
            "sms": debounce_sms_seconds or int(
                os.getenv("DEBOUNCE_SMS_SECONDS", str(DEFAULT_DEBOUNCE_SMS))
            ),
            "email": 30,  # Default for email, can be configured later
        }

    def get_debounce_time(self, channel: Channel) -> int:
        """Get the debounce time for a channel."""
        return self._debounce_times.get(channel, 30)

    def set_flush_callback(
        self,
        callback: Callable[[BufferedEvent], Coroutine[Any, Any, None]],
    ) -> None:
        """Set the callback to be called when buffer is flushed."""
        self._on_flush = callback

    async def buffer_message(
        self,
        channel: Channel,
        sender: str,
        content: str,
        sender_name: str | None = None,
        timestamp: str | None = None,
    ) -> bool:
        """
        Add a message to the buffer.

        If this is the first message in a new window, starts a timer
        that will flush the buffer after the debounce period.

        Args:
            channel: Message channel (telegram, sms, email)
            sender: Sender identifier (phone, username, email)
            content: Message content
            sender_name: Optional human-readable sender name
            timestamp: ISO 8601 timestamp (defaults to now)

        Returns:
            True if this is the first message in the window, False if added to existing buffer
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat()

        key = _get_buffer_key(sender, channel)
        is_first = key not in self._buffers

        if is_first:
            self._buffers[key] = BufferEntry(first_message_time=timestamp)

        entry = self._buffers[key]
        entry.messages.append(
            BufferedMessage(
                channel=channel,
                sender=sender,
                sender_name=sender_name,
                content=content,
                timestamp=timestamp,
            )
        )

        logger.debug(
            "Buffered message from %s/%s (count: %d, is_first: %s)",
            channel,
            sender,
            len(entry.messages),
            is_first,
        )

        if is_first:
            # Start the debounce timer
            debounce_time = self.get_debounce_time(channel)
            entry.timer_task = asyncio.create_task(
                self._flush_after_delay(key, debounce_time)
            )

        return is_first

    async def _flush_after_delay(self, key: str, delay_seconds: int) -> None:
        """Wait for debounce period then flush the buffer."""
        try:
            await asyncio.sleep(delay_seconds)
            await self._do_flush(key)
        except asyncio.CancelledError:
            logger.debug("Flush timer cancelled for %s", key)

    async def _do_flush(self, key: str) -> BufferedEvent | None:
        """Flush a buffer and call the callback."""
        if key not in self._buffers:
            return None

        entry = self._buffers.pop(key)

        if not entry.messages:
            return None

        # Combine messages
        combined_content = "\n".join(m.content for m in entry.messages)
        first_msg = entry.messages[0]

        event = BufferedEvent(
            channel=first_msg.channel,
            sender=first_msg.sender,
            sender_name=first_msg.sender_name,
            content=combined_content,
            timestamp=entry.first_message_time or first_msg.timestamp,
            message_count=len(entry.messages),
        )

        logger.info(
            "Flushing buffer for %s/%s: %d messages combined",
            event.channel,
            event.sender,
            event.message_count,
        )

        if self._on_flush:
            try:
                await self._on_flush(event)
            except Exception as e:
                logger.error("Error in flush callback: %s", e)

        return event

    async def flush_buffer(self, sender: str, channel: Channel) -> BufferedEvent | None:
        """
        Immediately flush a specific buffer.

        Cancels any pending timer and returns the combined messages.

        Args:
            sender: Sender identifier
            channel: Message channel

        Returns:
            BufferedEvent with combined messages, or None if buffer was empty
        """
        key = _get_buffer_key(sender, channel)

        if key not in self._buffers:
            return None

        entry = self._buffers[key]

        # Cancel the timer if running
        if entry.timer_task and not entry.timer_task.done():
            entry.timer_task.cancel()
            try:
                await entry.timer_task
            except asyncio.CancelledError:
                pass

        return await self._do_flush(key)

    def has_pending_messages(self, sender: str, channel: Channel) -> bool:
        """Check if there are pending messages for a sender/channel."""
        key = _get_buffer_key(sender, channel)
        return key in self._buffers

    def get_pending_count(self, sender: str, channel: Channel) -> int:
        """Get the number of pending messages for a sender/channel."""
        key = _get_buffer_key(sender, channel)
        if key not in self._buffers:
            return 0
        return len(self._buffers[key].messages)

    async def flush_all(self) -> list[BufferedEvent]:
        """
        Flush all pending buffers immediately.

        Useful for shutdown or testing.

        Returns:
            List of all flushed events
        """
        events = []
        keys = list(self._buffers.keys())

        for key in keys:
            # Parse sender and channel from key
            parts = key.split(":", 1)
            if len(parts) == 2:
                channel, sender = parts[0], parts[1]
                event = await self.flush_buffer(sender, channel)  # type: ignore
                if event:
                    events.append(event)

        return events

    def clear(self) -> None:
        """Clear all buffers without flushing (for testing)."""
        for entry in self._buffers.values():
            if entry.timer_task and not entry.timer_task.done():
                entry.timer_task.cancel()
        self._buffers.clear()


__all__ = [
    "MessageBuffer",
    "BufferedEvent",
    "BufferedMessage",
]
