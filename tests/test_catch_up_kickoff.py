"""
Unit tests for catch-up jorb kickoff in JorbSession.

Tests that catch-up jorbs use Sean-voice style context-recovery messages
instead of LLM calls.
"""

import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.jorb_session import (
    JorbSession,
    JorbSessionResponse,
    JorbAction,
    JorbProgress,
    create_jorb_session,
)
from services.jorb_storage import (
    Jorb,
    JorbContact,
    JorbMessage,
    JorbWithMessages,
)
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


@pytest.fixture
def sean_voice_personality():
    """Create sean-voice personality for testing."""
    return Personality(
        id="sean-voice",
        name="Sean Voice",
        description="Sean's casual communication style",
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
                persona="tech professional",
                background="Software engineer",
            ),
        ),
        system_prompt_additions=SystemPromptAdditions(),
        policy_overrides=PolicyOverrides(),
        model_preferences=ModelPreferences(temperature=0.8),
    )


@pytest.fixture
def catch_up_jorb():
    """Create a catch-up jorb (has 'Recover context' in plan)."""
    jorb = Jorb(
        id="jorb_catchup",
        name="Catch-up: hey quick question about",
        status="running",
        original_plan="Recover context for in-flight task. Original message: hey quick question about the reservation",
        personality="sean-voice",
    )
    jorb.contacts = [
        JorbContact(identifier="@magic", channel="telegram", name="Magic Concierge")
    ]
    return jorb


@pytest.fixture
def regular_jorb():
    """Create a regular jorb (NOT a catch-up)."""
    jorb = Jorb(
        id="jorb_regular",
        name="Hotel Booking",
        status="running",
        original_plan="Book a hotel in SF for March 17-21",
        personality="sean-voice",
    )
    jorb.contacts = [
        JorbContact(identifier="@magic", channel="telegram", name="Magic Concierge")
    ]
    return jorb


class TestIsCatchUpJorb:
    """Test _is_catch_up_jorb detection method."""

    def test_detects_catch_up_jorb(self, catch_up_jorb, sean_voice_personality):
        """Jorb with 'Recover context' in plan is detected as catch-up."""
        session = JorbSession(
            jorb=catch_up_jorb,
            messages=[],
            personality=sean_voice_personality,
        )
        assert session._is_catch_up_jorb() is True

    def test_regular_jorb_not_catch_up(self, regular_jorb, sean_voice_personality):
        """Regular jorb is NOT detected as catch-up."""
        session = JorbSession(
            jorb=regular_jorb,
            messages=[],
            personality=sean_voice_personality,
        )
        assert session._is_catch_up_jorb() is False


class TestKickoffCatchUpJorb:
    """Test _kickoff_catch_up_jorb method."""

    def test_returns_send_message_action(self, catch_up_jorb, sean_voice_personality):
        """Catch-up kickoff returns send_message action."""
        session = JorbSession(
            jorb=catch_up_jorb,
            messages=[],
            personality=sean_voice_personality,
        )
        response = session._kickoff_catch_up_jorb()

        assert response.action.type == "send_message"
        assert response.action.channel == "telegram"
        assert response.action.recipient == "@magic"

    def test_message_asks_for_context(self, catch_up_jorb, sean_voice_personality):
        """Catch-up message asks for context in casual way."""
        session = JorbSession(
            jorb=catch_up_jorb,
            messages=[],
            personality=sean_voice_personality,
        )
        response = session._kickoff_catch_up_jorb()

        # Should contain words about forgetting/catching up
        message_lower = response.action.content.lower()
        assert any(
            phrase in message_lower
            for phrase in ["sorry", "lost track", "remind me", "catch me up", "where"]
        )

    def test_message_is_lowercase_casual(self, catch_up_jorb, sean_voice_personality):
        """Catch-up message uses lowercase casual style."""
        session = JorbSession(
            jorb=catch_up_jorb,
            messages=[],
            personality=sean_voice_personality,
        )
        response = session._kickoff_catch_up_jorb()

        # Message should be lowercase (Sean's style)
        assert response.action.content == response.action.content.lower()

    def test_sets_awaiting_to_context_recovery(
        self, catch_up_jorb, sean_voice_personality
    ):
        """Catch-up kickoff sets awaiting to 'context_recovery'."""
        session = JorbSession(
            jorb=catch_up_jorb,
            messages=[],
            personality=sean_voice_personality,
        )
        response = session._kickoff_catch_up_jorb()

        assert response.progress is not None
        assert response.progress.awaiting == "context_recovery"

    def test_no_llm_call_zero_tokens(self, catch_up_jorb, sean_voice_personality):
        """Catch-up kickoff doesn't use LLM (0 tokens)."""
        session = JorbSession(
            jorb=catch_up_jorb,
            messages=[],
            personality=sean_voice_personality,
        )
        response = session._kickoff_catch_up_jorb()

        assert response.tokens_used == 0
        assert response.estimated_cost == 0.0

    def test_message_varies_for_natural_feel(
        self, catch_up_jorb, sean_voice_personality
    ):
        """Messages should vary between calls for natural feel."""
        session = JorbSession(
            jorb=catch_up_jorb,
            messages=[],
            personality=sean_voice_personality,
        )

        # Collect messages from multiple calls
        messages = set()
        for _ in range(20):
            response = session._kickoff_catch_up_jorb()
            messages.add(response.action.content)

        # Should have at least 2 different messages (randomized)
        assert len(messages) >= 2

    def test_no_contacts_returns_no_action(self, sean_voice_personality):
        """Jorb with no contacts returns no_action."""
        jorb = Jorb(
            id="jorb_no_contacts",
            name="Catch-up: no contacts",
            status="running",
            original_plan="Recover context for in-flight task. No contacts though.",
            personality="sean-voice",
        )
        # No contacts set

        session = JorbSession(
            jorb=jorb,
            messages=[],
            personality=sean_voice_personality,
        )
        response = session._kickoff_catch_up_jorb()

        assert response.action.type == "no_action"


class TestKickoffMethodRouting:
    """Test that kickoff() routes to catch-up handler correctly."""

    @pytest.mark.asyncio
    async def test_catch_up_jorb_skips_llm(self, catch_up_jorb, sean_voice_personality):
        """Catch-up jorb kickoff doesn't call LLM."""
        session = JorbSession(
            jorb=catch_up_jorb,
            messages=[],
            personality=sean_voice_personality,
            openai_api_key="test-key",
        )

        # Mock openai to verify it's NOT called
        with patch("services.jorb_session.openai") as mock_openai:
            response = await session.kickoff()

            # OpenAI should NOT be called
            mock_openai.OpenAI.assert_not_called()

        assert response.action.type == "send_message"
        assert response.progress.awaiting == "context_recovery"

    @pytest.mark.asyncio
    async def test_regular_jorb_uses_llm(self, regular_jorb, sean_voice_personality):
        """Regular jorb kickoff uses LLM (would call OpenAI)."""
        session = JorbSession(
            jorb=regular_jorb,
            messages=[],
            personality=sean_voice_personality,
            openai_api_key="test-key",
        )

        # Mock openai for regular jorb
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content='{"reasoning": "test", "action": {"type": "send_message", "channel": "telegram", "recipient": "@magic", "content": "Hi!"}}'
                )
            )
        ]
        mock_response.usage = MagicMock(prompt_tokens=100, completion_tokens=50)

        with patch("services.jorb_session.openai") as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.OpenAI.return_value = mock_client

            response = await session.kickoff()

            # OpenAI SHOULD be called for regular jorbs
            mock_openai.OpenAI.assert_called_once()

        assert response.action.type == "send_message"


class TestCreateJorbSessionIntegration:
    """Test integration with create_jorb_session factory."""

    @pytest.mark.asyncio
    async def test_catch_up_jorb_with_factory(self, catch_up_jorb):
        """Catch-up jorb created via factory works correctly."""
        jwm = JorbWithMessages(jorb=catch_up_jorb, messages=[])

        # Patch personality loader to return sean-voice
        with patch("services.jorb_session.get_personality_loader") as mock_loader:
            mock_personality = MagicMock()
            mock_personality.id = "sean-voice"
            mock_personality.model_preferences.temperature = 0.8
            mock_personality.model_preferences.preferred_model = None
            mock_personality.format_for_prompt.return_value = "Sean voice traits"

            loader_instance = MagicMock()
            loader_instance.get_or_default.return_value = mock_personality
            mock_loader.return_value = loader_instance

            session = create_jorb_session(jwm)
            response = await session.kickoff()

        assert response.action.type == "send_message"
        assert response.tokens_used == 0
        assert response.progress.awaiting == "context_recovery"
