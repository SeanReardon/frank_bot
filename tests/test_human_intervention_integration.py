"""
Integration tests for human intervention flow (Stream B).

Tests the end-to-end flow of human intervention detection and processing:
1. Telegram listener detects outgoing messages not in jorb_messages
2. Sean's direct messages route with is_human_intervention=True
3. Sean's messages are stored without triggering LLM response
4. Jorb progress is updated with intervention note
5. Jorb session learns from sean_direct messages

Uses mocked Telegram client and jorb storage.
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
from services.telegram_client import TelegramClientService, DispatchContext


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


class TestTelegramListenerDetectsOutgoing:
    """Test: Telegram listener detects outgoing messages not in jorb_messages."""

    @pytest.mark.asyncio
    async def test_outgoing_not_in_jorb_messages_detected_as_human(
        self, storage: JorbStorage
    ) -> None:
        """Outgoing message NOT found in jorb_messages is human intervention."""
        # Create a jorb (but don't add any messages)
        await storage.create_jorb(
            name="Test Jorb",
            plan="Test plan",
        )

        # Check if a message is from frank_bot (should be False since no messages stored)
        now = datetime.now(timezone.utc)
        is_frank_bot = await storage.is_frank_bot_message(
            content="Hey let me check on that",
            timestamp=now,
            time_window_seconds=10,
        )

        # Should NOT be identified as frank_bot message
        assert is_frank_bot is False

    @pytest.mark.asyncio
    async def test_outgoing_in_jorb_messages_skipped(
        self, storage: JorbStorage
    ) -> None:
        """Outgoing message found in jorb_messages is skipped (from frank_bot)."""
        jorb = await storage.create_jorb(
            name="Test Jorb",
            plan="Test plan",
        )

        # Store an outbound message (simulating frank_bot sent it)
        now = datetime.now(timezone.utc)
        msg = JorbMessage(
            id="",
            jorb_id=jorb.id,
            timestamp=now.isoformat(),
            direction="outbound",
            channel="telegram",
            sender="frank_bot",
            content="Hey let me check on that",
        )
        await storage.add_message(jorb_id=jorb.id, message=msg)

        # Check if the same message is from frank_bot
        is_frank_bot = await storage.is_frank_bot_message(
            content="Hey let me check on that",
            timestamp=now,
            time_window_seconds=10,
        )

        # Should be identified as frank_bot message
        assert is_frank_bot is True

    @pytest.mark.asyncio
    async def test_dispatch_context_for_human_intervention(self) -> None:
        """DispatchContext correctly marks human intervention."""
        # Test that DispatchContext can carry the is_human_intervention flag
        context = DispatchContext(is_self_sent=True, is_human_intervention=True)

        assert context.is_self_sent is True
        assert context.is_human_intervention is True


class TestSeanDirectMessagesRouteWithFlag:
    """Test: Sean's direct messages route with is_human_intervention=True."""

    @pytest.mark.asyncio
    async def test_switchboard_receives_human_intervention_flag(
        self, runner, storage
    ) -> None:
        """Switchboard route is called with is_human_intervention=True."""
        # Create a jorb with a contact
        jorb = await storage.create_jorb(
            name="Hotel Booking",
            plan="Book hotel in SF",
            contacts=[JorbContact(identifier="@magic", channel="telegram")],
        )
        await storage.update_jorb(jorb.id, status="running")

        # Create human intervention event
        event = IncomingEvent(
            channel="telegram",
            sender="@magic",
            sender_name="Magic Concierge",
            content="actually let's go with hotel nikko",
            timestamp=datetime.now(timezone.utc).isoformat(),
            is_human_intervention=True,
        )

        # Mock switchboard to capture the call
        routing_decision = RoutingDecision(
            jorb_id=jorb.id,
            confidence="high",
            reasoning="Contact match",
            is_human_intervention=True,
        )

        with patch.dict(os.environ, {"USE_SWITCHBOARD_MODE": "true"}):
            with patch(
                "services.agent_runner.get_switchboard"
            ) as mock_get_switchboard:
                mock_switchboard = MagicMock()
                mock_switchboard.route = AsyncMock(return_value=routing_decision)
                mock_get_switchboard.return_value = mock_switchboard

                await runner.process_incoming_message(event)

                # Verify is_human_intervention was passed to switchboard
                mock_switchboard.route.assert_called_once()
                call_kwargs = mock_switchboard.route.call_args.kwargs
                assert call_kwargs["is_human_intervention"] is True

    @pytest.mark.asyncio
    async def test_human_intervention_high_confidence_on_match(
        self, runner, storage
    ) -> None:
        """Human intervention gets high confidence when jorb matched."""
        jorb = await storage.create_jorb(
            name="Test Task",
            plan="Test plan",
            contacts=[JorbContact(identifier="@contact", channel="telegram")],
        )
        await storage.update_jorb(jorb.id, status="running")

        event = IncomingEvent(
            channel="telegram",
            sender="@contact",
            sender_name="Contact",
            content="quick update on the task",
            timestamp=datetime.now(timezone.utc).isoformat(),
            is_human_intervention=True,
        )

        routing_decision = RoutingDecision(
            jorb_id=jorb.id,
            confidence="high",  # Should be high for human intervention
            reasoning="Sean knows what he's doing",
            is_human_intervention=True,
        )

        with patch.dict(os.environ, {"USE_SWITCHBOARD_MODE": "true"}):
            with patch(
                "services.agent_runner.get_switchboard"
            ) as mock_get_switchboard:
                mock_switchboard = MagicMock()
                mock_switchboard.route = AsyncMock(return_value=routing_decision)
                mock_get_switchboard.return_value = mock_switchboard

                result = await runner.process_incoming_message(event)

                assert result.jorb_id == jorb.id
                assert result.action_taken == "human_intervention_recorded"


class TestSeanMessagesStoredWithoutLLM:
    """Test: Sean's messages are stored without triggering LLM response."""

    @pytest.mark.asyncio
    async def test_no_llm_call_for_human_intervention(
        self, runner, storage
    ) -> None:
        """LLM is NOT called for human intervention messages."""
        jorb = await storage.create_jorb(
            name="Hotel Booking",
            plan="Book hotel",
            contacts=[JorbContact(identifier="@magic", channel="telegram")],
        )
        await storage.update_jorb(jorb.id, status="running")

        event = IncomingEvent(
            channel="telegram",
            sender="@magic",
            sender_name="Magic",
            content="let me confirm the nikko booking",
            timestamp=datetime.now(timezone.utc).isoformat(),
            is_human_intervention=True,
        )

        routing_decision = RoutingDecision(
            jorb_id=jorb.id,
            confidence="high",
            reasoning="Contact match",
            is_human_intervention=True,
        )

        with patch.dict(os.environ, {"USE_SWITCHBOARD_MODE": "true"}):
            with patch(
                "services.agent_runner.get_switchboard"
            ) as mock_get_switchboard:
                mock_switchboard = MagicMock()
                mock_switchboard.route = AsyncMock(return_value=routing_decision)
                mock_get_switchboard.return_value = mock_switchboard

                # Mock jorb session to verify it's NOT called
                with patch(
                    "services.agent_runner.create_jorb_session"
                ) as mock_create_session:
                    result = await runner.process_incoming_message(event)

                    # JorbSession should NOT be created for human intervention
                    mock_create_session.assert_not_called()

        assert result.success is True
        assert result.action_taken == "human_intervention_recorded"

    @pytest.mark.asyncio
    async def test_message_stored_with_sean_direct_sender(
        self, runner, storage
    ) -> None:
        """Human intervention message stored with sender='sean_direct'."""
        jorb = await storage.create_jorb(
            name="Test Task",
            plan="Test plan",
            contacts=[JorbContact(identifier="@contact", channel="telegram")],
        )
        await storage.update_jorb(jorb.id, status="running")

        event = IncomingEvent(
            channel="telegram",
            sender="@contact",
            sender_name="Contact",
            content="I'll handle this one directly",
            timestamp=datetime.now(timezone.utc).isoformat(),
            is_human_intervention=True,
        )

        routing_decision = RoutingDecision(
            jorb_id=jorb.id,
            confidence="high",
            reasoning="Contact match",
            is_human_intervention=True,
        )

        with patch.dict(os.environ, {"USE_SWITCHBOARD_MODE": "true"}):
            with patch(
                "services.agent_runner.get_switchboard"
            ) as mock_get_switchboard:
                mock_switchboard = MagicMock()
                mock_switchboard.route = AsyncMock(return_value=routing_decision)
                mock_get_switchboard.return_value = mock_switchboard

                await runner.process_incoming_message(event)

        # Verify message was stored with sean_direct sender
        messages = await storage.get_messages(jorb.id)
        assert len(messages) == 1
        assert messages[0].sender == "sean_direct"
        assert messages[0].sender_name == "Sean"
        assert messages[0].direction == "outbound"
        assert messages[0].content == event.content


class TestJorbProgressUpdatedWithIntervention:
    """Test: Jorb progress is updated with intervention note."""

    @pytest.mark.asyncio
    async def test_progress_summary_includes_intervention_note(
        self, runner, storage
    ) -> None:
        """Jorb progress_summary is updated when Sean intervenes."""
        jorb = await storage.create_jorb(
            name="Hotel Booking",
            plan="Book hotel",
            contacts=[JorbContact(identifier="@magic", channel="telegram")],
        )
        await storage.update_jorb(jorb.id, status="running")

        event = IncomingEvent(
            channel="telegram",
            sender="@magic",
            sender_name="Magic",
            content="actually get the suite instead",
            timestamp=datetime.now(timezone.utc).isoformat(),
            is_human_intervention=True,
        )

        routing_decision = RoutingDecision(
            jorb_id=jorb.id,
            confidence="high",
            reasoning="Contact match",
            is_human_intervention=True,
        )

        with patch.dict(os.environ, {"USE_SWITCHBOARD_MODE": "true"}):
            with patch(
                "services.agent_runner.get_switchboard"
            ) as mock_get_switchboard:
                mock_switchboard = MagicMock()
                mock_switchboard.route = AsyncMock(return_value=routing_decision)
                mock_get_switchboard.return_value = mock_switchboard

                await runner.process_incoming_message(event)

        # Verify progress was updated
        updated_jorb = await storage.get_jorb(jorb.id)
        assert "Sean intervened directly" in updated_jorb.progress_summary
        assert "suite" in updated_jorb.progress_summary

    @pytest.mark.asyncio
    async def test_closure_words_mark_jorb_complete(
        self, runner, storage
    ) -> None:
        """Closure words in Sean's message mark jorb as complete."""
        jorb = await storage.create_jorb(
            name="Hotel Booking",
            plan="Book hotel",
            contacts=[JorbContact(identifier="@magic", channel="telegram")],
        )
        await storage.update_jorb(jorb.id, status="running")

        # Message with closure words
        event = IncomingEvent(
            channel="telegram",
            sender="@magic",
            sender_name="Magic",
            content="thanks! got the confirmation, all set",
            timestamp=datetime.now(timezone.utc).isoformat(),
            is_human_intervention=True,
        )

        routing_decision = RoutingDecision(
            jorb_id=jorb.id,
            confidence="high",
            reasoning="Contact match",
            is_human_intervention=True,
        )

        with patch.dict(os.environ, {"USE_SWITCHBOARD_MODE": "true"}):
            with patch(
                "services.agent_runner.get_switchboard"
            ) as mock_get_switchboard:
                mock_switchboard = MagicMock()
                mock_switchboard.route = AsyncMock(return_value=routing_decision)
                mock_get_switchboard.return_value = mock_switchboard

                await runner.process_incoming_message(event)

        # Verify jorb was marked complete
        updated_jorb = await storage.get_jorb(jorb.id)
        assert updated_jorb.status == "complete"


class TestJorbSessionLearnsFromSeanDirect:
    """Test: Jorb session learns from sean_direct messages."""

    @pytest.mark.asyncio
    async def test_sean_direct_messages_labeled_as_guidance(
        self, storage, temp_progress_path
    ) -> None:
        """sean_direct messages are labeled as 'GUIDANCE FROM PRINCIPAL' in context."""
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
            id="jorb_test123",
            name="Hotel Booking",
            status="running",
            original_plan="Book hotel",
            personality="sean-voice",
        )
        jorb.contacts = [
            JorbContact(identifier="@magic", channel="telegram", name="Magic")
        ]

        # Create messages including sean_direct
        messages = [
            JorbMessage(
                id="msg_001",
                jorb_id=jorb.id,
                timestamp="2026-01-31T10:00:00Z",
                direction="outbound",
                channel="telegram",
                sender="frank_bot",
                content="Looking for hotels in SF",
            ),
            JorbMessage(
                id="msg_002",
                jorb_id=jorb.id,
                timestamp="2026-01-31T11:00:00Z",
                direction="outbound",
                channel="telegram",
                sender="sean_direct",  # Sean's direct message
                sender_name="Sean",
                content="actually check hotel zetta too",
            ),
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

        with patch.dict(os.environ, {"PROGRESS_LOG_PATH": temp_progress_path}):
            session = JorbSession(
                jorb=jorb,
                messages=messages,
                personality=personality,
            )
            prompt = session._build_system_prompt()

        # Verify sean_direct message is labeled as guidance
        assert "GUIDANCE FROM PRINCIPAL" in prompt
        assert "hotel zetta" in prompt

    @pytest.mark.asyncio
    async def test_learning_instructions_added_for_sean_direct(
        self, storage, temp_progress_path
    ) -> None:
        """Learning instructions are added when sean_direct messages exist."""
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
            id="jorb_test456",
            name="Test Task",
            status="running",
            original_plan="Test",
            personality="sean-voice",
        )
        jorb.contacts = [
            JorbContact(identifier="@contact", channel="telegram")
        ]

        # Only sean_direct message
        messages = [
            JorbMessage(
                id="msg_001",
                jorb_id=jorb.id,
                timestamp="2026-01-31T10:00:00Z",
                direction="outbound",
                channel="telegram",
                sender="sean_direct",
                sender_name="Sean",
                content="hey just checking in",
            ),
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

        with patch.dict(os.environ, {"PROGRESS_LOG_PATH": temp_progress_path}):
            session = JorbSession(
                jorb=jorb,
                messages=messages,
                personality=personality,
            )
            prompt = session._build_system_prompt()

        # Verify learning instructions are present
        assert "Learning from Principal's Direct Messages" in prompt
        assert "preferred phrasing" in prompt


class TestEndToEndHumanInterventionFlow:
    """End-to-end integration test for complete human intervention flow."""

    @pytest.mark.asyncio
    async def test_complete_human_intervention_flow(
        self, storage, temp_progress_path
    ) -> None:
        """
        Complete flow:
        1. Create jorb
        2. Sean sends direct message (human intervention)
        3. Message is stored with sean_direct marker
        4. No LLM response triggered
        5. Progress updated
        6. Session can learn from the message
        """
        with patch.dict(os.environ, {"PROGRESS_LOG_PATH": temp_progress_path}):
            runner = AgentRunner(storage=storage, openai_api_key="test-api-key")

        # Step 1: Create jorb
        jorb = await storage.create_jorb(
            name="Hotel Booking",
            plan="Book a hotel in SF for March",
            contacts=[JorbContact(identifier="@magic", channel="telegram", name="Magic")],
            personality="sean-voice",
        )
        await storage.update_jorb(jorb.id, status="running")

        # Step 2: Sean sends direct message
        event = IncomingEvent(
            channel="telegram",
            sender="@magic",
            sender_name="Magic",
            content="hey can you also check hotel vitale? saw good reviews",
            timestamp=datetime.now(timezone.utc).isoformat(),
            is_human_intervention=True,
        )

        routing_decision = RoutingDecision(
            jorb_id=jorb.id,
            confidence="high",
            reasoning="Contact match - human intervention",
            is_human_intervention=True,
        )

        with patch.dict(os.environ, {"USE_SWITCHBOARD_MODE": "true"}):
            with patch(
                "services.agent_runner.get_switchboard"
            ) as mock_get_switchboard:
                mock_switchboard = MagicMock()
                mock_switchboard.route = AsyncMock(return_value=routing_decision)
                mock_get_switchboard.return_value = mock_switchboard

                # Step 3: Process - should NOT create jorb session
                with patch(
                    "services.agent_runner.create_jorb_session"
                ) as mock_session:
                    result = await runner.process_incoming_message(event)

                    # Verify no LLM call
                    mock_session.assert_not_called()

        # Step 4: Verify result
        assert result.success is True
        assert result.jorb_id == jorb.id
        assert result.action_taken == "human_intervention_recorded"
        assert result.message_sent is False  # No outbound message

        # Step 5: Verify message stored correctly
        messages = await storage.get_messages(jorb.id)
        assert len(messages) == 1
        msg = messages[0]
        assert msg.sender == "sean_direct"
        assert msg.sender_name == "Sean"
        assert msg.direction == "outbound"
        assert "hotel vitale" in msg.content

        # Step 6: Verify progress updated
        updated_jorb = await storage.get_jorb(jorb.id)
        assert "Sean intervened directly" in updated_jorb.progress_summary
        assert "hotel vitale" in updated_jorb.progress_summary

        # Step 7: Verify session can learn from the message
        from services.jorb_session import JorbSession
        from services.personality_loader import get_personality_loader

        personality = get_personality_loader().get("sean-voice")
        if personality:
            session = JorbSession(
                jorb=updated_jorb,
                messages=messages,
                personality=personality,
            )
            prompt = session._build_system_prompt()

            # Sean's message should be labeled as guidance
            assert "GUIDANCE FROM PRINCIPAL" in prompt
