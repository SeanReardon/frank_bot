"""
Integration tests for catch-up jorb flow (Stream C).

Tests the end-to-end flow of catch-up jorb creation and processing:
1. Trusted sender with unmatched message creates catch-up jorb
2. Catch-up jorb uses sean-voice personality
3. Catch-up kickoff message asks for context in Sean's style
4. Unknown sender with unmatched message is flagged, not jorbed
5. Magic's response to catch-up updates jorb plan with context

Uses mocked OpenAI, Telegram, and jorb storage.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Check if openai is available for tests
try:
    import openai
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

from services.agent_runner import (
    AgentRunner,
    IncomingEvent,
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


class TestTrustedSenderCreatesCatchUpJorb:
    """Test: Trusted sender with unmatched message creates catch-up jorb."""

    @pytest.mark.asyncio
    async def test_trusted_sender_creates_catch_up(
        self, runner, storage
    ) -> None:
        """Trusted sender with might_be_new_jorb creates catch-up jorb."""
        # First create a previous jorb so sender becomes trusted
        await storage.create_jorb(
            name="Previous Task",
            plan="Old task",
            contacts=[JorbContact(identifier="@magic", channel="telegram", name="Magic")],
        )

        # New message from same sender, no matching jorb
        event = IncomingEvent(
            channel="telegram",
            sender="@magic",
            sender_name="Magic Concierge",
            content="hey quick question about the dinner reservation next week",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        routing_decision = RoutingDecision(
            jorb_id=None,  # No match
            confidence="low",
            reasoning="No matching jorb",
            might_be_new_jorb=True,  # Looks like a new task
        )

        with patch.dict(os.environ, {"USE_SWITCHBOARD_MODE": "true"}):
            with patch(
                "services.agent_runner.get_switchboard"
            ) as mock_get_switchboard:
                mock_switchboard = MagicMock()
                mock_switchboard.route = AsyncMock(return_value=routing_decision)
                mock_get_switchboard.return_value = mock_switchboard

                # Mock kickoff to avoid actual message sending
                with patch.object(
                    runner, "kickoff_jorb", new_callable=AsyncMock
                ) as mock_kickoff:
                    mock_kickoff.return_value = MagicMock(message_sent=True)

                    result = await runner.process_incoming_message(event)

        # Verify catch-up jorb was created
        assert result.success is True
        assert result.action_taken == "catch_up_created"
        assert result.jorb_id is not None

        # Verify jorb properties
        jorb = await storage.get_jorb(result.jorb_id)
        assert jorb.name.startswith("Catch-up:")
        assert jorb.status == "running"
        # The name is truncated to ~30 chars, but full message is in plan
        assert "dinner reservation" in jorb.original_plan

    @pytest.mark.asyncio
    async def test_catch_up_jorb_plan_contains_recover_context(
        self, runner, storage
    ) -> None:
        """Catch-up jorb plan contains 'Recover context' and original message."""
        # Make sender trusted
        await storage.create_jorb(
            name="Previous Task",
            plan="Old task",
            contacts=[JorbContact(identifier="@magic", channel="telegram")],
        )

        event = IncomingEvent(
            channel="telegram",
            sender="@magic",
            sender_name="Magic",
            content="following up on the concert tickets",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        routing_decision = RoutingDecision(
            jorb_id=None,
            confidence="low",
            reasoning="No match",
            might_be_new_jorb=True,
        )

        with patch.dict(os.environ, {"USE_SWITCHBOARD_MODE": "true"}):
            with patch(
                "services.agent_runner.get_switchboard"
            ) as mock_get_switchboard:
                mock_switchboard = MagicMock()
                mock_switchboard.route = AsyncMock(return_value=routing_decision)
                mock_get_switchboard.return_value = mock_switchboard

                with patch.object(runner, "kickoff_jorb", new_callable=AsyncMock) as mock_kickoff:
                    mock_kickoff.return_value = MagicMock(message_sent=True)
                    result = await runner.process_incoming_message(event)

        jorb = await storage.get_jorb(result.jorb_id)
        assert "Recover context" in jorb.original_plan
        assert "concert tickets" in jorb.original_plan


class TestCatchUpJorbUsesSeanVoice:
    """Test: Catch-up jorb uses sean-voice personality."""

    @pytest.mark.asyncio
    async def test_catch_up_uses_sean_voice_personality(
        self, runner, storage
    ) -> None:
        """Catch-up jorb is created with sean-voice personality."""
        # Make sender trusted
        await storage.create_jorb(
            name="Previous Task",
            plan="Old task",
            contacts=[JorbContact(identifier="@magic", channel="telegram")],
        )

        event = IncomingEvent(
            channel="telegram",
            sender="@magic",
            sender_name="Magic",
            content="hey about that thing from yesterday",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        routing_decision = RoutingDecision(
            jorb_id=None,
            confidence="low",
            reasoning="No match",
            might_be_new_jorb=True,
        )

        with patch.dict(os.environ, {"USE_SWITCHBOARD_MODE": "true"}):
            with patch(
                "services.agent_runner.get_switchboard"
            ) as mock_get_switchboard:
                mock_switchboard = MagicMock()
                mock_switchboard.route = AsyncMock(return_value=routing_decision)
                mock_get_switchboard.return_value = mock_switchboard

                with patch.object(runner, "kickoff_jorb", new_callable=AsyncMock) as mock_kickoff:
                    mock_kickoff.return_value = MagicMock(message_sent=True)
                    result = await runner.process_incoming_message(event)

        jorb = await storage.get_jorb(result.jorb_id)
        assert jorb.personality == "sean-voice"


class TestCatchUpKickoffMessageStyle:
    """Test: Catch-up kickoff message asks for context in Sean's style."""

    @pytest.mark.asyncio
    async def test_kickoff_message_asks_for_context(self) -> None:
        """Catch-up kickoff message asks for context casually."""
        from services.jorb_session import JorbSession
        from services.personality_loader import (
            Personality,
            Traits,
            CommunicationStyle,
            DecisionMaking,
            Expertise,
            SystemPromptAdditions,
            PolicyOverrides,
            ModelPreferences,
        )

        jorb = Jorb(
            id="jorb_catchup_test",
            name="Catch-up: hey about the dinner",
            status="running",
            original_plan="Recover context for in-flight task. Original message: hey about the dinner reservation",
            personality="sean-voice",
        )
        jorb.contacts = [
            JorbContact(identifier="@magic", channel="telegram", name="Magic")
        ]

        personality = Personality(
            id="sean-voice",
            name="Sean Voice",
            description="Sean's casual style",
            traits=Traits(
                communication_style=CommunicationStyle(
                    tone="casual",
                    verbosity="very_concise",
                    formality=0.2,
                    emotiveness=0.3,
                    emoji_usage="never",
                ),
                decision_making=DecisionMaking(
                    risk_tolerance="balanced",
                    autonomy="autonomous",
                    patience_level="impatient",
                    negotiation_style="direct",
                ),
                expertise=Expertise(
                    domains=["tech"],
                    persona="tech pro",
                    background="Engineer",
                ),
            ),
            system_prompt_additions=SystemPromptAdditions(),
            policy_overrides=PolicyOverrides(),
            model_preferences=ModelPreferences(temperature=0.8),
        )

        session = JorbSession(
            jorb=jorb,
            messages=[],
            personality=personality,
        )

        response = session._kickoff_catch_up_jorb()

        # Verify action is send_message
        assert response.action.type == "send_message"
        assert response.action.channel == "telegram"
        assert response.action.recipient == "@magic"

        # Verify message asks for context in casual way
        message_lower = response.action.content.lower()
        assert any(
            phrase in message_lower
            for phrase in ["sorry", "lost track", "remind me", "catch me up", "where"]
        )

        # Verify message is lowercase (Sean's style)
        assert response.action.content == response.action.content.lower()

    @pytest.mark.asyncio
    async def test_kickoff_sets_awaiting_context_recovery(self) -> None:
        """Catch-up kickoff sets awaiting to 'context_recovery'."""
        from services.jorb_session import JorbSession
        from services.personality_loader import (
            Personality,
            Traits,
            CommunicationStyle,
            DecisionMaking,
            Expertise,
            SystemPromptAdditions,
            PolicyOverrides,
            ModelPreferences,
        )

        jorb = Jorb(
            id="jorb_catchup_test2",
            name="Catch-up: test",
            status="running",
            original_plan="Recover context for in-flight task. Original message: test",
            personality="sean-voice",
        )
        jorb.contacts = [
            JorbContact(identifier="@contact", channel="telegram")
        ]

        personality = Personality(
            id="sean-voice",
            name="Sean Voice",
            description="Sean's style",
            traits=Traits(
                communication_style=CommunicationStyle(
                    tone="casual",
                    verbosity="very_concise",
                    formality=0.2,
                    emotiveness=0.3,
                    emoji_usage="never",
                ),
                decision_making=DecisionMaking(
                    risk_tolerance="balanced",
                    autonomy="autonomous",
                    patience_level="impatient",
                    negotiation_style="direct",
                ),
                expertise=Expertise(
                    domains=["tech"],
                    persona="tech pro",
                    background="Engineer",
                ),
            ),
            system_prompt_additions=SystemPromptAdditions(),
            policy_overrides=PolicyOverrides(),
            model_preferences=ModelPreferences(temperature=0.8),
        )

        session = JorbSession(
            jorb=jorb,
            messages=[],
            personality=personality,
        )

        response = session._kickoff_catch_up_jorb()

        assert response.progress is not None
        assert response.progress.awaiting == "context_recovery"

    @pytest.mark.asyncio
    async def test_kickoff_no_llm_call(self) -> None:
        """Catch-up kickoff doesn't call LLM (0 tokens)."""
        from services.jorb_session import JorbSession
        from services.personality_loader import (
            Personality,
            Traits,
            CommunicationStyle,
            DecisionMaking,
            Expertise,
            SystemPromptAdditions,
            PolicyOverrides,
            ModelPreferences,
        )

        jorb = Jorb(
            id="jorb_catchup_test3",
            name="Catch-up: test",
            status="running",
            original_plan="Recover context for in-flight task. Original message: test",
            personality="sean-voice",
        )
        jorb.contacts = [
            JorbContact(identifier="@contact", channel="telegram")
        ]

        personality = Personality(
            id="sean-voice",
            name="Sean Voice",
            description="Sean's style",
            traits=Traits(
                communication_style=CommunicationStyle(
                    tone="casual",
                    verbosity="very_concise",
                    formality=0.2,
                    emotiveness=0.3,
                    emoji_usage="never",
                ),
                decision_making=DecisionMaking(
                    risk_tolerance="balanced",
                    autonomy="autonomous",
                    patience_level="impatient",
                    negotiation_style="direct",
                ),
                expertise=Expertise(
                    domains=["tech"],
                    persona="tech pro",
                    background="Engineer",
                ),
            ),
            system_prompt_additions=SystemPromptAdditions(),
            policy_overrides=PolicyOverrides(),
            model_preferences=ModelPreferences(temperature=0.8),
        )

        session = JorbSession(
            jorb=jorb,
            messages=[],
            personality=personality,
        )

        response = session._kickoff_catch_up_jorb()

        # Verify no tokens used (no LLM call)
        assert response.tokens_used == 0
        assert response.estimated_cost == 0.0


class TestUnknownSenderFlagged:
    """Test: Unknown sender with unmatched message is flagged, not jorbed."""

    @pytest.mark.asyncio
    async def test_unknown_sender_not_auto_jorbed(
        self, runner, storage
    ) -> None:
        """Unknown sender is flagged for review, not auto-jorbed."""
        # No previous jorbs with this sender - they're unknown
        event = IncomingEvent(
            channel="sms",
            sender="+15559876543",
            sender_name=None,
            content="Hi is this Sean? Got your number from...",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        routing_decision = RoutingDecision(
            jorb_id=None,
            confidence="low",
            reasoning="Unknown sender",
            might_be_new_jorb=True,  # Looks like a task, but unknown sender
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
                    result = await runner.process_incoming_message(event)
                finally:
                    if original_class:
                        services.telegram_bot.TelegramBot = original_class

        # Verify flagged, not jorbed
        assert result.action_taken == "flagged_for_review"
        assert result.jorb_id is None

        # Verify no jorb was created
        jorbs = await storage.list_jorbs()
        assert len(jorbs) == 0

    @pytest.mark.asyncio
    async def test_unknown_sender_triggers_notification(
        self, runner, storage
    ) -> None:
        """Unknown sender triggers Telegram notification to Sean."""
        event = IncomingEvent(
            channel="sms",
            sender="+15559876543",
            sender_name=None,
            content="Hey can you help me with something?",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        routing_decision = RoutingDecision(
            jorb_id=None,
            confidence="low",
            reasoning="Unknown sender",
            might_be_new_jorb=True,
        )

        with patch.dict(os.environ, {"USE_SWITCHBOARD_MODE": "true"}):
            with patch(
                "services.agent_runner.get_switchboard"
            ) as mock_get_switchboard:
                mock_switchboard = MagicMock()
                mock_switchboard.route = AsyncMock(return_value=routing_decision)
                mock_get_switchboard.return_value = mock_switchboard

                # Mock TelegramBot to capture notification
                import services.telegram_bot
                original_class = getattr(services.telegram_bot, "TelegramBot", None)
                mock_bot = MagicMock()
                mock_bot.send_notification = AsyncMock()
                mock_class = MagicMock(return_value=mock_bot)

                try:
                    services.telegram_bot.TelegramBot = mock_class
                    await runner.process_incoming_message(event)

                    # Verify notification was sent
                    mock_bot.send_notification.assert_called_once()
                    notification = mock_bot.send_notification.call_args[0][0]
                    assert "Unknown sender" in notification
                    assert "+15559876543" in notification
                finally:
                    if original_class:
                        services.telegram_bot.TelegramBot = original_class


class TestMagicResponseUpdatesJorb:
    """Test: Magic's response to catch-up updates jorb plan with context."""

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_OPENAI, reason="openai package not installed")
    async def test_response_updates_jorb_with_context(
        self, runner, storage
    ) -> None:
        """Magic's response updates the catch-up jorb with context."""
        # Create a catch-up jorb (simulating it was created by previous message)
        jorb = await storage.create_jorb(
            name="Catch-up: hey about the hotel",
            plan="Recover context for in-flight task. Original message: hey about the hotel booking",
            contacts=[JorbContact(identifier="@magic", channel="telegram", name="Magic")],
            personality="sean-voice",
        )
        await storage.update_jorb(jorb.id, status="running", awaiting="context_recovery")

        # Magic responds with context
        event = IncomingEvent(
            channel="telegram",
            sender="@magic",
            sender_name="Magic",
            content="Oh right! You wanted Hotel Nikko for March 17-21, checking for suite availability",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        # Mock agent response that updates the plan
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "reasoning": "Magic provided context about the hotel booking request",
            "action": {
                "type": "no_action",
            },
            "task_update": {
                "progress_note": "Context recovered: Hotel Nikko booking for March 17-21, checking suite availability",
            },
        })
        mock_response.usage = MagicMock(prompt_tokens=100, completion_tokens=50)

        with patch("services.agent_runner.openai") as mock_openai:
            mock_client = MagicMock()
            mock_openai.OpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            result = await runner.process_incoming_message(event)

        assert result.success is True
        assert result.jorb_id == jorb.id

        # Verify jorb was updated with context
        updated_jorb = await storage.get_jorb(jorb.id)
        assert "Hotel Nikko" in (updated_jorb.progress_summary or "")


class TestEndToEndCatchUpFlow:
    """End-to-end integration test for complete catch-up jorb flow."""

    @pytest.mark.asyncio
    async def test_complete_catch_up_flow(
        self, storage, temp_progress_path
    ) -> None:
        """
        Complete flow:
        1. Create previous jorb (establishes trust)
        2. Trusted sender sends unmatched message
        3. Catch-up jorb created with sean-voice
        4. Kickoff message sent in Sean's style
        5. Incoming message stored
        """
        with patch.dict(os.environ, {"PROGRESS_LOG_PATH": temp_progress_path}):
            runner = AgentRunner(storage=storage, openai_api_key="test-api-key")

        # Step 1: Create previous jorb (establishes trust)
        old_jorb = await storage.create_jorb(
            name="Previous Hotel Booking",
            plan="Previous task with Magic",
            contacts=[JorbContact(identifier="@magic", channel="telegram", name="Magic Concierge")],
        )
        await storage.update_jorb(old_jorb.id, status="complete")

        # Step 2: Trusted sender sends new unmatched message
        event = IncomingEvent(
            channel="telegram",
            sender="@magic",
            sender_name="Magic Concierge",
            content="hey quick follow-up about the spa reservation we discussed",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        routing_decision = RoutingDecision(
            jorb_id=None,
            confidence="low",
            reasoning="No matching jorb",
            might_be_new_jorb=True,
        )

        # Track kickoff call
        kickoff_calls = []
        async def mock_kickoff(jorb):
            kickoff_calls.append(jorb)
            return MagicMock(message_sent=True)

        with patch.dict(os.environ, {"USE_SWITCHBOARD_MODE": "true"}):
            with patch(
                "services.agent_runner.get_switchboard"
            ) as mock_get_switchboard:
                mock_switchboard = MagicMock()
                mock_switchboard.route = AsyncMock(return_value=routing_decision)
                mock_get_switchboard.return_value = mock_switchboard

                with patch.object(runner, "kickoff_jorb", side_effect=mock_kickoff):
                    result = await runner.process_incoming_message(event)

        # Step 3: Verify catch-up jorb created
        assert result.success is True
        assert result.action_taken == "catch_up_created"
        assert result.jorb_id is not None

        catch_up_jorb = await storage.get_jorb(result.jorb_id)
        assert catch_up_jorb.name.startswith("Catch-up:")
        # The name is truncated to ~30 chars, but full message is in plan
        assert "spa reservation" in catch_up_jorb.original_plan

        # Step 4: Verify sean-voice personality
        assert catch_up_jorb.personality == "sean-voice"

        # Step 5: Verify recovery plan
        assert "Recover context" in catch_up_jorb.original_plan
        assert "spa reservation" in catch_up_jorb.original_plan

        # Step 6: Verify kickoff was called
        assert len(kickoff_calls) == 1
        assert kickoff_calls[0].id == catch_up_jorb.id

        # Step 7: Verify incoming message was stored
        messages = await storage.get_messages(catch_up_jorb.id)
        assert len(messages) == 1
        assert messages[0].direction == "inbound"
        assert "spa reservation" in messages[0].content

        # Step 8: Verify jorb has sender as contact
        contacts = catch_up_jorb.contacts
        assert len(contacts) == 1
        assert contacts[0].identifier == "@magic"


class TestTrustedSenderDetection:
    """Integration tests for trusted sender detection."""

    @pytest.mark.asyncio
    async def test_contact_from_any_jorb_is_trusted(
        self, runner, storage
    ) -> None:
        """Contact from any previous jorb (any status) is trusted."""
        # Create completed jorb with Magic
        await storage.create_jorb(
            name="Old Task",
            plan="Old task",
            contacts=[JorbContact(identifier="@magic", channel="telegram")],
        )

        # Magic should be trusted
        is_trusted = await runner.is_trusted_sender("@magic")
        assert is_trusted is True

    @pytest.mark.asyncio
    async def test_never_contacted_is_not_trusted(
        self, runner, storage
    ) -> None:
        """Sender who has never been a jorb contact is not trusted."""
        is_trusted = await runner.is_trusted_sender("+15559999999")
        assert is_trusted is False

    @pytest.mark.asyncio
    async def test_phone_number_normalization(
        self, runner, storage
    ) -> None:
        """Phone numbers are normalized for comparison."""
        # Create jorb with specific phone format
        await storage.create_jorb(
            name="Phone Task",
            plan="Task via SMS",
            contacts=[JorbContact(identifier="+15551234567", channel="sms")],
        )

        # Different formats should still be trusted
        assert await runner.is_trusted_sender("+15551234567") is True
        assert await runner.is_trusted_sender("15551234567") is True
        assert await runner.is_trusted_sender("5551234567") is True
