"""
Unit tests for catch-up jorb creation in AgentRunner.

Tests Stream C: Catch-up jorb creation for in-flight tasks from trusted senders.
"""

import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.agent_runner import (
    AgentRunner,
    IncomingEvent,
    JorbPolicy,
    ProcessingResult,
)
from services.jorb_storage import (
    Jorb,
    JorbContact,
    JorbMessage,
    JorbStorage,
    JorbWithMessages,
)
from services.switchboard import RoutingDecision


@pytest.fixture
def temp_db_path():
    """Create a temporary database file path."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield f.name
    if os.path.exists(f.name):
        os.unlink(f.name)


@pytest.fixture
def temp_progress_path():
    """Create a temporary progress log file path."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        yield f.name
    if os.path.exists(f.name):
        os.unlink(f.name)


@pytest.fixture
def storage(temp_db_path):
    """Create a JorbStorage instance with temp database."""
    return JorbStorage(db_path=temp_db_path)


@pytest.fixture
def runner(storage, temp_progress_path):
    """Create an AgentRunner with storage and fake API key."""
    with patch.dict(os.environ, {"PROGRESS_LOG_PATH": temp_progress_path}):
        return AgentRunner(storage=storage, openai_api_key="test-api-key")


@pytest.fixture
def existing_jorb_with_contact():
    """Create an existing jorb with Magic as a contact (for trusted sender detection)."""
    jorb = Jorb(
        id="jorb_existing",
        name="Previous Task with Magic",
        status="complete",
        original_plan="An old task",
    )
    jorb.contacts = [
        JorbContact(identifier="@magic", channel="telegram", name="Magic Concierge")
    ]
    return jorb


@pytest.fixture
def trusted_sender_event():
    """Create an event from a trusted sender (Magic) with no matching jorb."""
    return IncomingEvent(
        channel="telegram",
        sender="@magic",
        sender_name="Magic Concierge",
        content="hey quick question about the reservation next week",
        timestamp=datetime.now(timezone.utc).isoformat(),
        message_count=1,
    )


@pytest.fixture
def unknown_sender_event():
    """Create an event from an unknown sender."""
    return IncomingEvent(
        channel="sms",
        sender="+15559876543",
        sender_name=None,
        content="Hi is this Sean? I got your number from...",
        timestamp=datetime.now(timezone.utc).isoformat(),
        message_count=1,
    )


class TestCatchUpJorbCreation:
    """Test _create_catch_up_jorb method."""

    @pytest.mark.asyncio
    async def test_creates_jorb_with_correct_name(
        self, runner, storage, trusted_sender_event
    ):
        """Catch-up jorb has name starting with 'Catch-up:'."""
        result = await runner._create_catch_up_jorb(trusted_sender_event)

        assert result.success is True
        assert result.jorb_id is not None

        jorb = await storage.get_jorb(result.jorb_id)
        assert jorb.name.startswith("Catch-up:")
        assert "hey quick question about the" in jorb.name

    @pytest.mark.asyncio
    async def test_creates_jorb_with_running_status(
        self, runner, storage, trusted_sender_event
    ):
        """Catch-up jorb is created with running status."""
        result = await runner._create_catch_up_jorb(trusted_sender_event)

        jorb = await storage.get_jorb(result.jorb_id)
        assert jorb.status == "running"

    @pytest.mark.asyncio
    async def test_creates_jorb_with_recovery_plan(
        self, runner, storage, trusted_sender_event
    ):
        """Catch-up jorb plan contains 'Recover context' and original message."""
        result = await runner._create_catch_up_jorb(trusted_sender_event)

        jorb = await storage.get_jorb(result.jorb_id)
        assert "Recover context" in jorb.original_plan
        assert trusted_sender_event.content in jorb.original_plan

    @pytest.mark.asyncio
    async def test_creates_jorb_with_sean_voice_personality(
        self, runner, storage, trusted_sender_event
    ):
        """Catch-up jorb uses sean-voice personality."""
        result = await runner._create_catch_up_jorb(trusted_sender_event)

        jorb = await storage.get_jorb(result.jorb_id)
        assert jorb.personality == "sean-voice"

    @pytest.mark.asyncio
    async def test_creates_jorb_with_sender_as_contact(
        self, runner, storage, trusted_sender_event
    ):
        """Catch-up jorb has sender as contact."""
        result = await runner._create_catch_up_jorb(trusted_sender_event)

        jorb = await storage.get_jorb(result.jorb_id)
        contacts = jorb.contacts
        assert len(contacts) == 1
        assert contacts[0].identifier == trusted_sender_event.sender
        assert contacts[0].channel == trusted_sender_event.channel

    @pytest.mark.asyncio
    async def test_stores_incoming_message(
        self, runner, storage, trusted_sender_event
    ):
        """Catch-up jorb stores the incoming message."""
        result = await runner._create_catch_up_jorb(trusted_sender_event)

        messages = await storage.get_messages(result.jorb_id)
        assert len(messages) == 1
        assert messages[0].direction == "inbound"
        assert messages[0].content == trusted_sender_event.content

    @pytest.mark.asyncio
    async def test_returns_catch_up_created_action(
        self, runner, storage, trusted_sender_event
    ):
        """Result has action_taken='catch_up_created'."""
        result = await runner._create_catch_up_jorb(trusted_sender_event)

        assert result.action_taken == "catch_up_created"

    @pytest.mark.asyncio
    async def test_kicks_off_jorb(
        self, runner, storage, trusted_sender_event
    ):
        """Catch-up jorb is kicked off after creation."""
        # Mock the kickoff to verify it's called
        with patch.object(runner, "kickoff_jorb", new_callable=AsyncMock) as mock_kickoff:
            mock_kickoff.return_value = MagicMock(message_sent=True)
            result = await runner._create_catch_up_jorb(trusted_sender_event)

            # Kickoff should have been called
            mock_kickoff.assert_called_once()
            call_args = mock_kickoff.call_args
            kickoff_jorb = call_args[0][0]  # First positional arg
            assert kickoff_jorb.name.startswith("Catch-up:")


class TestFlagForReview:
    """Test _flag_for_review method."""

    @pytest.mark.asyncio
    async def test_returns_flagged_for_review_action(
        self, runner, unknown_sender_event
    ):
        """Result has action_taken='flagged_for_review'."""
        result = await runner._flag_for_review(unknown_sender_event)

        assert result.action_taken == "flagged_for_review"
        assert result.success is True
        assert result.jorb_id is None

    @pytest.mark.asyncio
    async def test_tries_to_send_telegram_notification(
        self, runner, unknown_sender_event
    ):
        """Attempts to send Telegram notification to Sean."""
        # Import the module to patch the class in its namespace
        import services.telegram_bot

        original_class = getattr(services.telegram_bot, "TelegramBot", None)
        mock_bot = MagicMock()
        mock_bot.send_notification = AsyncMock()
        mock_class = MagicMock(return_value=mock_bot)

        try:
            services.telegram_bot.TelegramBot = mock_class
            await runner._flag_for_review(unknown_sender_event)

            mock_bot.send_notification.assert_called_once()
            notification = mock_bot.send_notification.call_args[0][0]
            assert "Unknown sender" in notification
            assert unknown_sender_event.sender in notification
        finally:
            if original_class:
                services.telegram_bot.TelegramBot = original_class

    @pytest.mark.asyncio
    async def test_does_not_create_jorb(
        self, runner, storage, unknown_sender_event
    ):
        """Does NOT create a jorb for unknown senders."""
        await runner._flag_for_review(unknown_sender_event)

        jorbs = await storage.list_jorbs()
        assert len(jorbs) == 0


class TestProcessIncomingMessageCatchUp:
    """Test full process_incoming_message flow with catch-up jorb creation."""

    @pytest.mark.asyncio
    async def test_trusted_sender_creates_catch_up_jorb(
        self, runner, storage, existing_jorb_with_contact, trusted_sender_event
    ):
        """Trusted sender with no match (not new) creates catch-up jorb."""
        # First create an existing jorb so sender becomes trusted
        await storage.create_jorb(
            name=existing_jorb_with_contact.name,
            plan=existing_jorb_with_contact.original_plan,
            contacts=existing_jorb_with_contact.contacts,
        )

        # Mock switchboard to return no match and not a new jorb
        routing_decision = RoutingDecision(
            jorb_id=None,
            confidence="low",
            reasoning="No matching jorb found",
            might_be_new_jorb=False,
        )

        with patch.dict(os.environ, {"USE_SWITCHBOARD_MODE": "true"}):
            with patch(
                "services.agent_runner.get_switchboard"
            ) as mock_get_switchboard:
                mock_switchboard = MagicMock()
                mock_switchboard.route = AsyncMock(return_value=routing_decision)
                mock_get_switchboard.return_value = mock_switchboard

                # Mock kickoff to avoid LLM call
                with patch.object(
                    runner, "kickoff_jorb", new_callable=AsyncMock
                ) as mock_kickoff:
                    mock_kickoff.return_value = MagicMock(message_sent=False)

                    result = await runner.process_incoming_message(
                        trusted_sender_event
                    )

        assert result.success is True
        assert result.action_taken == "catch_up_created"
        assert result.jorb_id is not None

        # Verify jorb was created
        jorb = await storage.get_jorb(result.jorb_id)
        assert jorb.name.startswith("Catch-up:")
        assert jorb.personality == "sean-voice"

    @pytest.mark.asyncio
    async def test_unknown_sender_flagged_for_review(
        self, runner, storage, unknown_sender_event
    ):
        """Unknown sender with might_be_new_jorb is flagged, not auto-jorbed."""
        # Mock switchboard to return no match but might_be_new_jorb=True
        routing_decision = RoutingDecision(
            jorb_id=None,
            confidence="low",
            reasoning="No matching jorb found",
            might_be_new_jorb=True,
        )

        with patch.dict(os.environ, {"USE_SWITCHBOARD_MODE": "true"}):
            with patch(
                "services.agent_runner.get_switchboard"
            ) as mock_get_switchboard:
                mock_switchboard = MagicMock()
                mock_switchboard.route = AsyncMock(return_value=routing_decision)
                mock_get_switchboard.return_value = mock_switchboard

                # Mock TelegramBot to avoid actual notification
                import services.telegram_bot
                original_class = getattr(services.telegram_bot, "TelegramBot", None)
                mock_bot = MagicMock()
                mock_bot.send_notification = AsyncMock()
                services.telegram_bot.TelegramBot = MagicMock(return_value=mock_bot)

                try:
                    result = await runner.process_incoming_message(
                        unknown_sender_event
                    )
                finally:
                    if original_class:
                        services.telegram_bot.TelegramBot = original_class

        assert result.action_taken == "flagged_for_review"
        assert result.jorb_id is None

        # Verify no jorb was created
        jorbs = await storage.list_jorbs()
        assert len(jorbs) == 0

    @pytest.mark.asyncio
    async def test_might_be_new_jorb_false_returns_no_match(
        self, runner, storage, trusted_sender_event
    ):
        """When might_be_new_jorb=False and sender is trusted, creates a catch-up jorb."""
        # Create existing jorb so sender is trusted
        existing = await storage.create_jorb(
            name="Previous Task",
            plan="Old task",
            contacts=[JorbContact(identifier="@magic", channel="telegram")],
        )

        # Mock switchboard to return no match and might_be_new_jorb=False
        routing_decision = RoutingDecision(
            jorb_id=None,
            confidence="low",
            reasoning="Random message, not a task",
            might_be_new_jorb=False,
        )

        with patch.dict(os.environ, {"USE_SWITCHBOARD_MODE": "true"}):
            with patch(
                "services.agent_runner.get_switchboard"
            ) as mock_get_switchboard:
                mock_switchboard = MagicMock()
                mock_switchboard.route = AsyncMock(return_value=routing_decision)
                mock_get_switchboard.return_value = mock_switchboard

                # Mock kickoff to avoid LLM call
                with patch.object(runner, "kickoff_jorb", new_callable=AsyncMock) as mock_kickoff:
                    mock_kickoff.return_value = MagicMock(message_sent=False)

                    result = await runner.process_incoming_message(trusted_sender_event)

        assert result.action_taken == "catch_up_created"
        assert result.jorb_id is not None


class TestTrustedSenderIntegration:
    """Integration tests for trusted sender detection in catch-up flow."""

    @pytest.mark.asyncio
    async def test_previous_jorb_contact_is_trusted(
        self, runner, storage
    ):
        """Sender who was a contact on any previous jorb is trusted."""
        # Create completed jorb with the sender
        await storage.create_jorb(
            name="Old Task",
            plan="Some old task",
            contacts=[JorbContact(identifier="@magic", channel="telegram")],
        )

        is_trusted = await runner.is_trusted_sender("@magic")
        assert is_trusted is True

    @pytest.mark.asyncio
    async def test_new_sender_is_not_trusted(
        self, runner, storage
    ):
        """Sender who has never been a jorb contact is not trusted."""
        is_trusted = await runner.is_trusted_sender("+15559999999")
        assert is_trusted is False

    @pytest.mark.asyncio
    async def test_normalized_phone_matching(
        self, runner, storage
    ):
        """Phone numbers are normalized for trusted sender detection."""
        # Create jorb with normalized phone
        await storage.create_jorb(
            name="Phone Task",
            plan="Task via SMS",
            contacts=[JorbContact(identifier="+15551234567", channel="sms")],
        )

        # Check with different formats
        assert await runner.is_trusted_sender("+15551234567") is True
        assert await runner.is_trusted_sender("15551234567") is True
        assert await runner.is_trusted_sender("5551234567") is True
