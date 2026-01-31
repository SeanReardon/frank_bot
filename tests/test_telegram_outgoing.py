"""
Unit tests for Telegram outgoing message processing.

Tests verify that outgoing messages are correctly classified as
frank_bot messages (skipped) or human intervention (processed).
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from services.jorb_storage import JorbStorage, JorbMessage


class TestIsFrankBotMessage:
    """Tests for JorbStorage.is_frank_bot_message method."""

    @pytest.fixture
    def storage(self, tmp_path) -> JorbStorage:
        """Create a JorbStorage instance with temp database."""
        db_path = tmp_path / "test_jorbs.db"
        return JorbStorage(db_path=str(db_path))

    @pytest.mark.asyncio
    async def test_no_messages_returns_false(self, storage: JorbStorage) -> None:
        """Returns False when no messages exist."""
        result = await storage.is_frank_bot_message(
            content="Hello world",
            timestamp=datetime.now(timezone.utc),
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_matching_message_returns_true(self, storage: JorbStorage) -> None:
        """Returns True when matching outbound message exists."""
        # Create a jorb with a message
        jorb = await storage.create_jorb(
            name="Test Jorb",
            plan="Test plan",
        )

        # Store an outbound message
        now = datetime.now(timezone.utc)
        msg = JorbMessage(
            id="",  # Will be generated
            jorb_id=jorb.id,
            timestamp=now.isoformat(),
            direction="outbound",
            channel="telegram",
            sender="frank_bot",
            content="Hello world",
        )
        await storage.add_message(jorb_id=jorb.id, message=msg)

        # Check if a similar message is from frank_bot
        result = await storage.is_frank_bot_message(
            content="Hello world",
            timestamp=now,
            time_window_seconds=10,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_substring_match_returns_true(self, storage: JorbStorage) -> None:
        """Returns True when content is a substring match."""
        jorb = await storage.create_jorb(name="Test", plan="Test")

        now = datetime.now(timezone.utc)
        msg = JorbMessage(
            id="",
            jorb_id=jorb.id,
            timestamp=now.isoformat(),
            direction="outbound",
            channel="telegram",
            sender="frank_bot",
            content="Hello world, how are you?",
        )
        await storage.add_message(jorb_id=jorb.id, message=msg)

        # Check with partial content (substring)
        result = await storage.is_frank_bot_message(
            content="Hello world",
            timestamp=now,
            time_window_seconds=10,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_case_insensitive_match(self, storage: JorbStorage) -> None:
        """Match is case insensitive."""
        jorb = await storage.create_jorb(name="Test", plan="Test")

        now = datetime.now(timezone.utc)
        msg = JorbMessage(
            id="",
            jorb_id=jorb.id,
            timestamp=now.isoformat(),
            direction="outbound",
            channel="telegram",
            sender="frank_bot",
            content="HELLO WORLD",
        )
        await storage.add_message(jorb_id=jorb.id, message=msg)

        result = await storage.is_frank_bot_message(
            content="hello world",
            timestamp=now,
            time_window_seconds=10,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_outside_time_window_returns_false(self, storage: JorbStorage) -> None:
        """Returns False when message is outside time window."""
        from datetime import timedelta

        jorb = await storage.create_jorb(name="Test", plan="Test")

        now = datetime.now(timezone.utc)
        msg = JorbMessage(
            id="",
            jorb_id=jorb.id,
            timestamp=now.isoformat(),
            direction="outbound",
            channel="telegram",
            sender="frank_bot",
            content="Hello world",
        )
        await storage.add_message(jorb_id=jorb.id, message=msg)

        # Check with timestamp far in the future
        future_time = now + timedelta(hours=1)
        result = await storage.is_frank_bot_message(
            content="Hello world",
            timestamp=future_time,
            time_window_seconds=5,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_inbound_message_not_matched(self, storage: JorbStorage) -> None:
        """Inbound messages are not matched (only outbound)."""
        jorb = await storage.create_jorb(name="Test", plan="Test")

        now = datetime.now(timezone.utc)
        # Store an INBOUND message (not outbound)
        msg = JorbMessage(
            id="",
            jorb_id=jorb.id,
            timestamp=now.isoformat(),
            direction="inbound",
            channel="telegram",
            sender="contact",
            content="Hello world",
        )
        await storage.add_message(jorb_id=jorb.id, message=msg)

        result = await storage.is_frank_bot_message(
            content="Hello world",
            timestamp=now,
            time_window_seconds=10,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_accepts_iso_string_timestamp(self, storage: JorbStorage) -> None:
        """Accepts ISO format string as timestamp."""
        jorb = await storage.create_jorb(name="Test", plan="Test")

        now = datetime.now(timezone.utc)
        msg = JorbMessage(
            id="",
            jorb_id=jorb.id,
            timestamp=now.isoformat(),
            direction="outbound",
            channel="telegram",
            sender="frank_bot",
            content="Test message",
        )
        await storage.add_message(jorb_id=jorb.id, message=msg)

        result = await storage.is_frank_bot_message(
            content="Test message",
            timestamp=now.isoformat(),
            time_window_seconds=10,
        )
        assert result is True


class TestDispatchContext:
    """Tests for DispatchContext dataclass."""

    def test_dispatch_context_defaults(self) -> None:
        """DispatchContext has correct default values."""
        from services.telegram_client import DispatchContext

        ctx = DispatchContext()
        assert ctx.is_self_sent is False
        assert ctx.is_human_intervention is False

    def test_dispatch_context_with_values(self) -> None:
        """DispatchContext can be created with custom values."""
        from services.telegram_client import DispatchContext

        ctx = DispatchContext(is_self_sent=True, is_human_intervention=True)
        assert ctx.is_self_sent is True
        assert ctx.is_human_intervention is True


class TestTelegramOutgoingDispatch:
    """Tests for outgoing message dispatch in TelegramClientService."""

    @pytest.mark.asyncio
    async def test_frank_bot_messages_skipped(self) -> None:
        """Messages from frank_bot are not dispatched to handlers."""
        from services.telegram_client import TelegramClientService, DispatchContext

        # Track handler calls
        handler_calls = []

        async def mock_handler(event, context: DispatchContext):
            handler_calls.append((event, context))

        service = TelegramClientService()
        service.register_message_handler(mock_handler)

        # Create mock event for outgoing message
        mock_event = MagicMock()
        mock_event.message.text = "Test message"
        mock_event.message.date = datetime.now(timezone.utc)

        # Mock storage to return True (is frank_bot message)
        with patch("services.jorb_storage.JorbStorage") as mock_storage_cls:
            mock_storage = MagicMock()
            mock_storage.is_frank_bot_message = AsyncMock(return_value=True)
            mock_storage_cls.return_value = mock_storage

            await service._dispatch_outgoing_to_handlers(mock_event)

        # Handler should NOT have been called
        assert len(handler_calls) == 0

    @pytest.mark.asyncio
    async def test_human_intervention_dispatched(self) -> None:
        """Sean's direct messages are dispatched with is_human_intervention=True."""
        from services.telegram_client import TelegramClientService, DispatchContext

        # Track handler calls
        handler_calls = []

        async def mock_handler(event, context: DispatchContext):
            handler_calls.append((event, context))

        service = TelegramClientService()
        service.register_message_handler(mock_handler)

        # Create mock event for outgoing message
        mock_event = MagicMock()
        mock_event.message.text = "Direct message from Sean"
        mock_event.message.date = datetime.now(timezone.utc)

        # Mock storage to return False (NOT a frank_bot message)
        with patch("services.jorb_storage.JorbStorage") as mock_storage_cls:
            mock_storage = MagicMock()
            mock_storage.is_frank_bot_message = AsyncMock(return_value=False)
            mock_storage_cls.return_value = mock_storage

            await service._dispatch_outgoing_to_handlers(mock_event)

        # Handler SHOULD have been called
        assert len(handler_calls) == 1
        event, context = handler_calls[0]
        assert context.is_self_sent is True
        assert context.is_human_intervention is True

    @pytest.mark.asyncio
    async def test_empty_outgoing_message_skipped(self) -> None:
        """Empty outgoing messages are skipped."""
        from services.telegram_client import TelegramClientService, DispatchContext

        handler_calls = []

        async def mock_handler(event, context: DispatchContext):
            handler_calls.append((event, context))

        service = TelegramClientService()
        service.register_message_handler(mock_handler)

        # Create mock event with empty text
        mock_event = MagicMock()
        mock_event.message.text = ""
        mock_event.message.date = datetime.now(timezone.utc)

        await service._dispatch_outgoing_to_handlers(mock_event)

        # Handler should NOT have been called
        assert len(handler_calls) == 0


class TestTelegramIncomingDispatch:
    """Tests for incoming message dispatch updates."""

    @pytest.mark.asyncio
    async def test_incoming_has_context(self) -> None:
        """Incoming messages are dispatched with context (is_self_sent=False)."""
        from services.telegram_client import TelegramClientService, DispatchContext
        from telethon.tl.types import User

        handler_calls = []

        async def mock_handler(event, context: DispatchContext):
            handler_calls.append((event, context))

        service = TelegramClientService()
        service.register_message_handler(mock_handler)

        # Create mock event
        mock_event = MagicMock()
        mock_event.out = False

        # Create mock sender (mutual contact)
        mock_sender = MagicMock(spec=User)
        mock_sender.first_name = "Test"
        mock_sender.username = "testuser"
        mock_sender.bot = False
        mock_sender.mutual_contact = True

        mock_event.get_sender = AsyncMock(return_value=mock_sender)

        await service._dispatch_to_handlers(mock_event)

        # Handler should have been called with context
        assert len(handler_calls) == 1
        event, context = handler_calls[0]
        assert context.is_self_sent is False
        assert context.is_human_intervention is False
