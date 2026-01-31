"""
Unit tests for JorbSession learning from Sean's direct messages.

Tests that sean_direct messages are labeled as guidance from principal
and that learnings about Sean's style are recorded properly.
"""

import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from services.jorb_session import (
    JorbSession,
    JorbSessionResponse,
    JorbAction,
    JorbProgress,
    _format_message_for_history,
    _is_sean_direct_message,
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
def temp_progress_path():
    """Create a temporary progress log file path."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        yield f.name
    if os.path.exists(f.name):
        os.unlink(f.name)


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
def sample_jorb():
    """Create a sample jorb."""
    jorb = Jorb(
        id="jorb_test123",
        name="Hotel Booking",
        status="running",
        original_plan="Book a hotel in SF",
        personality="sean-voice",
    )
    jorb.contacts = [
        JorbContact(identifier="@magic", channel="telegram", name="Magic Concierge")
    ]
    return jorb


@pytest.fixture
def regular_outbound_message():
    """Create a regular outbound message (from frank_bot)."""
    return JorbMessage(
        id="msg_001",
        jorb_id="jorb_test123",
        timestamp="2026-01-31T10:00:00Z",
        direction="outbound",
        channel="telegram",
        sender="frank_bot",
        recipient="@magic",
        content="Hi Magic! I'm looking for a hotel in SF for next week.",
    )


@pytest.fixture
def sean_direct_message():
    """Create a sean_direct message (Sean's direct intervention)."""
    return JorbMessage(
        id="msg_002",
        jorb_id="jorb_test123",
        timestamp="2026-01-31T11:00:00Z",
        direction="outbound",
        channel="telegram",
        sender="sean_direct",  # Special marker
        sender_name="Sean",
        recipient="@magic",
        content="hey actually can you check hotel zetta too? thanks",
    )


@pytest.fixture
def inbound_message():
    """Create an inbound message from contact."""
    return JorbMessage(
        id="msg_003",
        jorb_id="jorb_test123",
        timestamp="2026-01-31T12:00:00Z",
        direction="inbound",
        channel="telegram",
        sender="@magic",
        sender_name="Magic Concierge",
        content="Sure! I'll check Hotel Zetta for you.",
    )


class TestIsSeanDirectMessage:
    """Test _is_sean_direct_message helper."""

    def test_detects_sean_direct_message(self, sean_direct_message):
        """Messages with sender='sean_direct' are detected."""
        assert _is_sean_direct_message(sean_direct_message) is True

    def test_regular_outbound_not_sean_direct(self, regular_outbound_message):
        """Regular outbound messages are not sean_direct."""
        assert _is_sean_direct_message(regular_outbound_message) is False

    def test_inbound_not_sean_direct(self, inbound_message):
        """Inbound messages are not sean_direct."""
        assert _is_sean_direct_message(inbound_message) is False


class TestFormatMessageForHistory:
    """Test _format_message_for_history with sean_direct marking."""

    def test_marks_sean_direct_in_formatted_output(self, sean_direct_message):
        """sean_direct messages have is_sean_direct=True in output."""
        formatted = _format_message_for_history(sean_direct_message)
        assert formatted.get("is_sean_direct") is True

    def test_regular_message_no_sean_direct_flag(self, regular_outbound_message):
        """Regular messages don't have is_sean_direct flag."""
        formatted = _format_message_for_history(regular_outbound_message)
        assert "is_sean_direct" not in formatted


class TestBuildSystemPromptWithSeanDirect:
    """Test system prompt building with sean_direct messages."""

    def test_labels_sean_direct_as_guidance_from_principal(
        self,
        sample_jorb,
        sean_voice_personality,
        sean_direct_message,
        regular_outbound_message,
        temp_progress_path,
    ):
        """sean_direct messages are labeled as GUIDANCE FROM PRINCIPAL."""
        with patch.dict(os.environ, {"PROGRESS_LOG_PATH": temp_progress_path}):
            session = JorbSession(
                jorb=sample_jorb,
                messages=[regular_outbound_message, sean_direct_message],
                personality=sean_voice_personality,
            )
            prompt = session._build_system_prompt()

        assert "GUIDANCE FROM PRINCIPAL" in prompt
        assert "hey actually can you check hotel zetta too" in prompt

    def test_adds_learning_instruction_when_sean_direct_present(
        self,
        sample_jorb,
        sean_voice_personality,
        sean_direct_message,
        temp_progress_path,
    ):
        """Learning instructions are added when sean_direct messages exist."""
        with patch.dict(os.environ, {"PROGRESS_LOG_PATH": temp_progress_path}):
            session = JorbSession(
                jorb=sample_jorb,
                messages=[sean_direct_message],
                personality=sean_voice_personality,
            )
            prompt = session._build_system_prompt()

        assert "Learning from Principal's Direct Messages" in prompt
        assert "preferred phrasing" in prompt

    def test_no_learning_instruction_without_sean_direct(
        self,
        sample_jorb,
        sean_voice_personality,
        regular_outbound_message,
        temp_progress_path,
    ):
        """No learning instructions when no sean_direct messages."""
        with patch.dict(os.environ, {"PROGRESS_LOG_PATH": temp_progress_path}):
            session = JorbSession(
                jorb=sample_jorb,
                messages=[regular_outbound_message],
                personality=sean_voice_personality,
            )
            prompt = session._build_system_prompt()

        assert "Learning from Principal's Direct Messages" not in prompt


class TestHasSeanDirectMessages:
    """Test has_sean_direct_messages method."""

    def test_returns_true_when_present(
        self,
        sample_jorb,
        sean_voice_personality,
        sean_direct_message,
        temp_progress_path,
    ):
        """Returns True when session has sean_direct messages."""
        with patch.dict(os.environ, {"PROGRESS_LOG_PATH": temp_progress_path}):
            session = JorbSession(
                jorb=sample_jorb,
                messages=[sean_direct_message],
                personality=sean_voice_personality,
            )
        assert session.has_sean_direct_messages() is True

    def test_returns_false_when_absent(
        self,
        sample_jorb,
        sean_voice_personality,
        regular_outbound_message,
        temp_progress_path,
    ):
        """Returns False when session has no sean_direct messages."""
        with patch.dict(os.environ, {"PROGRESS_LOG_PATH": temp_progress_path}):
            session = JorbSession(
                jorb=sample_jorb,
                messages=[regular_outbound_message],
                personality=sean_voice_personality,
            )
        assert session.has_sean_direct_messages() is False


class TestRecordLearning:
    """Test _record_learning with Sean style detection."""

    def test_detects_sean_style_learning(
        self, sample_jorb, sean_voice_personality, temp_progress_path
    ):
        """Style-related learnings are routed to Sean style recording."""
        with patch.dict(os.environ, {"PROGRESS_LOG_PATH": temp_progress_path}):
            session = JorbSession(
                jorb=sample_jorb,
                messages=[],
                personality=sean_voice_personality,
            )

            # Mock the progress log
            mock_progress_log = MagicMock()
            session._progress_log = mock_progress_log

            # Record a style learning
            session._record_learning("Sean's style prefers brevity and lowercase")

            # Should use contact_behavior category with Sean's style subject
            mock_progress_log.add_learning.assert_called_once()
            call_kwargs = mock_progress_log.add_learning.call_args.kwargs
            assert call_kwargs["category"] == "contact_behavior"
            assert call_kwargs["subject"] == "Sean's communication style"
            assert call_kwargs["confidence"] == "high"

    def test_regular_learning_uses_contact_subject(
        self, sample_jorb, sean_voice_personality, temp_progress_path
    ):
        """Non-style learnings use contact as subject."""
        with patch.dict(os.environ, {"PROGRESS_LOG_PATH": temp_progress_path}):
            session = JorbSession(
                jorb=sample_jorb,
                messages=[],
                personality=sean_voice_personality,
            )

            # Mock the progress log
            mock_progress_log = MagicMock()
            session._progress_log = mock_progress_log

            # Record a regular learning
            session._record_learning("Magic responds faster in the morning")

            # Should use contact subject
            call_kwargs = mock_progress_log.add_learning.call_args.kwargs
            assert call_kwargs["subject"] == "Magic Concierge"
            assert call_kwargs["category"] == "tip"


class TestRecordSeanStyleLearning:
    """Test _record_sean_style_learning method directly."""

    def test_records_with_high_confidence(
        self, sample_jorb, sean_voice_personality, temp_progress_path
    ):
        """Sean style learnings are recorded with high confidence."""
        with patch.dict(os.environ, {"PROGRESS_LOG_PATH": temp_progress_path}):
            session = JorbSession(
                jorb=sample_jorb,
                messages=[],
                personality=sean_voice_personality,
            )

            mock_progress_log = MagicMock()
            session._progress_log = mock_progress_log

            session._record_sean_style_learning("Sean uses lowercase and no punctuation")

            call_kwargs = mock_progress_log.add_learning.call_args.kwargs
            assert call_kwargs["confidence"] == "high"
            assert call_kwargs["subject"] == "Sean's communication style"

    def test_uses_contact_behavior_category(
        self, sample_jorb, sean_voice_personality, temp_progress_path
    ):
        """Sean style learnings use contact_behavior category."""
        with patch.dict(os.environ, {"PROGRESS_LOG_PATH": temp_progress_path}):
            session = JorbSession(
                jorb=sample_jorb,
                messages=[],
                personality=sean_voice_personality,
            )

            mock_progress_log = MagicMock()
            session._progress_log = mock_progress_log

            session._record_sean_style_learning("Prefers hey over hi")

            call_kwargs = mock_progress_log.add_learning.call_args.kwargs
            assert call_kwargs["category"] == "contact_behavior"
