"""
Unit tests for human intervention handling in AgentRunner.

Tests Stream B: Sean's direct messages are captured and recorded without
triggering LLM responses.
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
def sample_jorb():
    """Create a sample jorb for hotel booking with Magic."""
    jorb = Jorb(
        id="jorb_12345678",
        name="Hotel Booking",
        status="running",
        original_plan="Book a hotel in SF for March 17-21",
        progress_summary="Contacted Magic, waiting for response",
        awaiting="Hotel options from Magic",
        personality="sean-voice",
    )
    jorb.contacts = [
        JorbContact(identifier="@magic", channel="telegram", name="Magic Concierge")
    ]
    return jorb


@pytest.fixture
def human_intervention_event():
    """Create an incoming event representing Sean's direct message."""
    return IncomingEvent(
        channel="telegram",
        sender="@magic",
        sender_name="Magic Concierge",
        content="ok let's go with hotel nikko",  # No closure words
        timestamp=datetime.now(timezone.utc).isoformat(),
        message_count=1,
        is_human_intervention=True,  # Sean sent this directly
    )


@pytest.fixture
def closure_event():
    """Create an event with closure words."""
    return IncomingEvent(
        channel="telegram",
        sender="@magic",
        sender_name="Magic Concierge",
        content="thanks! got the confirmation, all set",
        timestamp=datetime.now(timezone.utc).isoformat(),
        message_count=1,
        is_human_intervention=True,
    )


class TestIncomingEventDataclass:
    """Test IncomingEvent dataclass with is_human_intervention field."""

    def test_default_is_human_intervention_is_false(self):
        """is_human_intervention defaults to False."""
        event = IncomingEvent(
            channel="telegram",
            sender="@test",
            sender_name=None,
            content="hello",
            timestamp="2026-01-31T00:00:00Z",
        )
        assert event.is_human_intervention is False

    def test_is_human_intervention_can_be_set_true(self):
        """is_human_intervention can be set to True."""
        event = IncomingEvent(
            channel="telegram",
            sender="@test",
            sender_name=None,
            content="hello",
            timestamp="2026-01-31T00:00:00Z",
            is_human_intervention=True,
        )
        assert event.is_human_intervention is True


class TestClosureWordDetection:
    """Test the _check_closure_words helper method."""

    def test_detects_thanks(self, runner):
        """Detects 'thanks' as closure word."""
        assert runner._check_closure_words("thanks!") is True
        assert runner._check_closure_words("Thanks so much") is True

    def test_detects_done(self, runner):
        """Detects 'done' as closure word."""
        assert runner._check_closure_words("done") is True
        assert runner._check_closure_words("We're all done here") is True

    def test_detects_perfect(self, runner):
        """Detects 'perfect' as closure word."""
        assert runner._check_closure_words("perfect, thanks!") is True

    def test_detects_got_it(self, runner):
        """Detects 'got it' as closure word."""
        assert runner._check_closure_words("got it") is True

    def test_detects_all_set(self, runner):
        """Detects 'all set' as closure word."""
        assert runner._check_closure_words("all set for tomorrow") is True

    def test_no_closure_for_regular_message(self, runner):
        """Regular messages don't trigger closure."""
        assert runner._check_closure_words("what time should we meet?") is False
        assert runner._check_closure_words("let me check") is False
        assert runner._check_closure_words("hotel nikko is available") is False
        assert runner._check_closure_words("I'll book that one") is False


class TestStoreHumanInterventionMessage:
    """Test storing human intervention messages with sean_direct marker."""

    @pytest.mark.asyncio
    async def test_stores_message_with_sean_direct_marker(
        self, runner, storage, sample_jorb, human_intervention_event
    ):
        """Human intervention messages are stored with sender='sean_direct'."""
        # Create jorb first
        await storage.create_jorb(
            name=sample_jorb.name,
            plan=sample_jorb.original_plan,
            contacts=sample_jorb.contacts,
        )
        jorbs = await storage.list_jorbs()
        jorb_id = jorbs[0].id

        # Store human intervention message
        msg_id = await runner.store_human_intervention_message(
            jorb_id, human_intervention_event
        )

        # Verify message was stored correctly
        messages = await storage.get_messages(jorb_id)
        assert len(messages) == 1

        msg = messages[0]
        assert msg.sender == "sean_direct"  # Special marker
        assert msg.sender_name == "Sean"
        assert msg.direction == "outbound"  # Sean sent TO the contact
        assert msg.content == human_intervention_event.content
        assert msg.recipient == human_intervention_event.sender

    @pytest.mark.asyncio
    async def test_increments_messages_out_counter(
        self, runner, storage, sample_jorb, human_intervention_event
    ):
        """Human intervention increments messages_out metric."""
        # Create jorb
        jorb = await storage.create_jorb(
            name=sample_jorb.name,
            plan=sample_jorb.original_plan,
            contacts=sample_jorb.contacts,
        )

        # Store human intervention message
        await runner.store_human_intervention_message(jorb.id, human_intervention_event)

        # Check metrics
        updated_jorb = await storage.get_jorb(jorb.id)
        assert updated_jorb.messages_out == 1


class TestHandleHumanIntervention:
    """Test the _handle_human_intervention method."""

    @pytest.mark.asyncio
    async def test_does_not_trigger_llm_response(
        self, runner, storage, sample_jorb, human_intervention_event
    ):
        """Human intervention does NOT call LLM for response."""
        # Create jorb
        jorb = await storage.create_jorb(
            name=sample_jorb.name,
            plan=sample_jorb.original_plan,
            contacts=sample_jorb.contacts,
            personality="sean-voice",
        )
        matched_jorb = JorbWithMessages(jorb=jorb, messages=[])

        # Mock jorb session to verify it's NOT called
        with patch("services.agent_runner.create_jorb_session") as mock_session:
            result = await runner._handle_human_intervention(
                jorb.id, matched_jorb, human_intervention_event
            )

            # Session should NOT be created
            mock_session.assert_not_called()

        assert result.success is True
        assert result.action_taken == "human_intervention_recorded"

    @pytest.mark.asyncio
    async def test_updates_progress_summary(
        self, runner, storage, sample_jorb, human_intervention_event
    ):
        """Human intervention updates jorb progress_summary."""
        # Create jorb
        jorb = await storage.create_jorb(
            name=sample_jorb.name,
            plan=sample_jorb.original_plan,
            contacts=sample_jorb.contacts,
        )
        matched_jorb = JorbWithMessages(jorb=jorb, messages=[])

        await runner._handle_human_intervention(
            jorb.id, matched_jorb, human_intervention_event
        )

        # Check progress was updated
        updated_jorb = await storage.get_jorb(jorb.id)
        assert "Sean intervened directly" in updated_jorb.progress_summary
        assert "hotel nikko" in updated_jorb.progress_summary

    @pytest.mark.asyncio
    async def test_closure_words_mark_jorb_complete(
        self, runner, storage, sample_jorb, closure_event
    ):
        """Closure words in Sean's message mark jorb as complete."""
        # Create jorb
        jorb = await storage.create_jorb(
            name=sample_jorb.name,
            plan=sample_jorb.original_plan,
            contacts=sample_jorb.contacts,
        )
        matched_jorb = JorbWithMessages(jorb=jorb, messages=[])

        await runner._handle_human_intervention(jorb.id, matched_jorb, closure_event)

        # Check jorb was marked complete
        updated_jorb = await storage.get_jorb(jorb.id)
        assert updated_jorb.status == "complete"

    @pytest.mark.asyncio
    async def test_non_closure_message_keeps_jorb_running(
        self, runner, storage, sample_jorb, human_intervention_event
    ):
        """Non-closure messages keep jorb in running status."""
        # Create jorb as running
        jorb = await storage.create_jorb(
            name=sample_jorb.name,
            plan=sample_jorb.original_plan,
            contacts=sample_jorb.contacts,
        )
        await storage.update_jorb(jorb.id, status="running")
        matched_jorb = JorbWithMessages(jorb=jorb, messages=[])

        await runner._handle_human_intervention(
            jorb.id, matched_jorb, human_intervention_event
        )

        # Check jorb is still running
        updated_jorb = await storage.get_jorb(jorb.id)
        assert updated_jorb.status == "running"


class TestProcessIncomingMessageWithHumanIntervention:
    """Test the full process_incoming_message flow with human intervention."""

    @pytest.mark.asyncio
    async def test_human_intervention_routed_correctly(
        self, runner, storage, sample_jorb, human_intervention_event
    ):
        """Human intervention messages are routed to correct jorb and recorded."""
        # Create jorb
        jorb = await storage.create_jorb(
            name=sample_jorb.name,
            plan=sample_jorb.original_plan,
            contacts=sample_jorb.contacts,
        )
        await storage.update_jorb(jorb.id, status="running")

        # Mock switchboard to return the jorb
        routing_decision = RoutingDecision(
            jorb_id=jorb.id,
            confidence="high",
            reasoning="Exact contact match",
            is_human_intervention=True,
        )

        with patch.dict(os.environ, {"USE_SWITCHBOARD_MODE": "true"}):
            with patch(
                "services.agent_runner.get_switchboard"
            ) as mock_get_switchboard:
                mock_switchboard = MagicMock()
                mock_switchboard.route = AsyncMock(return_value=routing_decision)
                mock_get_switchboard.return_value = mock_switchboard

                # Process the message
                result = await runner.process_incoming_message(human_intervention_event)

        assert result.success is True
        assert result.jorb_id == jorb.id
        assert result.action_taken == "human_intervention_recorded"
        assert result.message_sent is False

        # Verify message was stored with sean_direct marker
        messages = await storage.get_messages(jorb.id)
        assert len(messages) == 1
        assert messages[0].sender == "sean_direct"

    @pytest.mark.asyncio
    async def test_human_intervention_passes_flag_to_switchboard(
        self, runner, storage, sample_jorb, human_intervention_event
    ):
        """is_human_intervention flag is passed to switchboard."""
        # Create jorb
        jorb = await storage.create_jorb(
            name=sample_jorb.name,
            plan=sample_jorb.original_plan,
            contacts=sample_jorb.contacts,
        )
        await storage.update_jorb(jorb.id, status="running")

        routing_decision = RoutingDecision(
            jorb_id=jorb.id,
            confidence="high",
            reasoning="Exact contact match",
            is_human_intervention=True,
        )

        with patch.dict(os.environ, {"USE_SWITCHBOARD_MODE": "true"}):
            with patch(
                "services.agent_runner.get_switchboard"
            ) as mock_get_switchboard:
                mock_switchboard = MagicMock()
                mock_switchboard.route = AsyncMock(return_value=routing_decision)
                mock_get_switchboard.return_value = mock_switchboard

                await runner.process_incoming_message(human_intervention_event)

                # Verify is_human_intervention was passed
                call_kwargs = mock_switchboard.route.call_args.kwargs
                assert call_kwargs["is_human_intervention"] is True

    @pytest.mark.asyncio
    async def test_human_intervention_no_match_might_new_jorb_flags_for_review(
        self, runner, storage, human_intervention_event
    ):
        """Human intervention with no jorb match and might_be_new_jorb flags for review."""
        routing_decision = RoutingDecision(
            jorb_id=None,
            confidence="low",
            reasoning="No matching jorb",
            might_be_new_jorb=True,
            is_human_intervention=True,
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
                    result = await runner.process_incoming_message(human_intervention_event)
                finally:
                    if original_class:
                        services.telegram_bot.TelegramBot = original_class

        # Unknown sender with might_be_new_jorb gets flagged for review
        assert result.jorb_id is None
        assert result.action_taken == "flagged_for_review"

    @pytest.mark.asyncio
    async def test_human_intervention_no_match_no_new_jorb_returns_no_match(
        self, runner, storage, human_intervention_event
    ):
        """Human intervention with no jorb match and might_be_new_jorb=False returns no_match."""
        routing_decision = RoutingDecision(
            jorb_id=None,
            confidence="low",
            reasoning="Random message",
            might_be_new_jorb=False,  # Not suggesting this is a new task
            is_human_intervention=True,
        )

        with patch.dict(os.environ, {"USE_SWITCHBOARD_MODE": "true"}):
            with patch(
                "services.agent_runner.get_switchboard"
            ) as mock_get_switchboard:
                mock_switchboard = MagicMock()
                mock_switchboard.route = AsyncMock(return_value=routing_decision)
                mock_get_switchboard.return_value = mock_switchboard

                result = await runner.process_incoming_message(human_intervention_event)

        assert result.jorb_id is None
        assert result.action_taken == "no_match"


class TestEnrichEventPreservesHumanIntervention:
    """Test that _enrich_event_with_contact preserves is_human_intervention."""

    @pytest.mark.asyncio
    async def test_preserves_flag_when_enriching_sms(self, runner):
        """is_human_intervention is preserved when enriching SMS event."""
        event = IncomingEvent(
            channel="sms",
            sender="+15551234567",
            sender_name=None,
            content="test message",
            timestamp=datetime.now(timezone.utc).isoformat(),
            is_human_intervention=True,
        )

        # Import ContactLookup at module scope for proper patching
        import services.contact_lookup

        # Mock contact lookup to return a contact
        original_class = services.contact_lookup.ContactLookup
        mock_lookup = MagicMock()
        mock_contact = MagicMock()
        mock_contact.name = "Test Contact"
        mock_lookup.lookup.return_value = mock_contact

        try:
            services.contact_lookup.ContactLookup = MagicMock(return_value=mock_lookup)
            enriched = await runner._enrich_event_with_contact(event)
        finally:
            services.contact_lookup.ContactLookup = original_class

        assert enriched.is_human_intervention is True
        assert enriched.sender_name == "Test Contact"

    @pytest.mark.asyncio
    async def test_preserves_flag_when_no_enrichment_needed(self, runner):
        """is_human_intervention is preserved when event already has sender_name."""
        event = IncomingEvent(
            channel="telegram",
            sender="@magic",
            sender_name="Magic Concierge",
            content="test message",
            timestamp=datetime.now(timezone.utc).isoformat(),
            is_human_intervention=True,
        )

        enriched = await runner._enrich_event_with_contact(event)

        assert enriched.is_human_intervention is True
        assert enriched is event  # Same object returned

    @pytest.mark.asyncio
    async def test_preserves_flag_when_contact_lookup_fails(self, runner):
        """is_human_intervention is preserved when contact lookup fails."""
        event = IncomingEvent(
            channel="sms",
            sender="+15551234567",
            sender_name=None,
            content="test message",
            timestamp=datetime.now(timezone.utc).isoformat(),
            is_human_intervention=True,
        )

        # Import ContactLookup at module scope for proper patching
        import services.contact_lookup

        # Mock contact lookup to return None (no contact found)
        original_class = services.contact_lookup.ContactLookup
        mock_lookup = MagicMock()
        mock_lookup.lookup.return_value = None

        try:
            services.contact_lookup.ContactLookup = MagicMock(return_value=mock_lookup)
            enriched = await runner._enrich_event_with_contact(event)
        finally:
            services.contact_lookup.ContactLookup = original_class

        # Event should be returned unchanged (same object)
        assert enriched is event
        assert enriched.is_human_intervention is True
