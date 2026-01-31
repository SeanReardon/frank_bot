"""
Integration tests for Sean voice capture flow (Stream A).

Tests the complete flow from message fetching through SEAN.md generation
and personality loading.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from services.style_analyzer import StyleAnalyzer
from services.personality_loader import PersonalityLoader, get_personality_loader


class TestStyleAnalyzerDateFiltering:
    """Test that style analyzer correctly filters by date."""

    @pytest.fixture
    def mock_messages(self) -> list[MagicMock]:
        """Create messages spanning different dates."""
        messages = []
        # Messages before cutoff (2026-01-01)
        for i in range(5):
            msg = MagicMock()
            msg.text = f"Pre-cutoff message {i}"
            msg.date = f"2025-12-{20 + i}T10:00:00+00:00"
            msg.is_outgoing = True
            messages.append(msg)

        # Messages after cutoff (should not appear)
        for i in range(3):
            msg = MagicMock()
            msg.text = f"Post-cutoff message {i}"
            msg.date = f"2026-01-{10 + i}T10:00:00+00:00"
            msg.is_outgoing = True
            messages.append(msg)

        return messages

    @pytest.mark.asyncio
    async def test_fetch_filters_by_before_date(
        self, mock_messages: list[MagicMock]
    ) -> None:
        """fetch_authentic_messages only returns messages before cutoff date."""
        mock_telegram = MagicMock()
        # Simulate Telegram returning all messages, but with date filtering
        mock_telegram.get_all_messages = AsyncMock(
            return_value=[m for m in mock_messages if "2025" in m.date]
        )

        analyzer = StyleAnalyzer(telegram_service=mock_telegram)
        before_date = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        messages = await analyzer.fetch_authentic_messages(
            chat_id="@TestChat",
            before_date=before_date,
        )

        # Should only get pre-cutoff messages
        assert len(messages) == 5
        for msg in messages:
            assert "2025" in msg.date

        # Verify call parameters
        mock_telegram.get_all_messages.assert_called_once_with(
            chat_id="@TestChat",
            before_date=before_date,
            direction_filter="outgoing",
        )

    @pytest.mark.asyncio
    async def test_fetch_uses_default_cutoff(self) -> None:
        """fetch_authentic_messages defaults to 2026-01-01 cutoff."""
        mock_telegram = MagicMock()
        mock_telegram.get_all_messages = AsyncMock(return_value=[])

        analyzer = StyleAnalyzer(telegram_service=mock_telegram)
        await analyzer.fetch_authentic_messages(chat_id="@TestChat")

        call_args = mock_telegram.get_all_messages.call_args
        before_date = call_args.kwargs["before_date"]
        assert before_date.year == 2026
        assert before_date.month == 1
        assert before_date.day == 1


class TestStyleAnalyzerHedgingExtraction:
    """Test that style analyzer extracts hedging patterns correctly."""

    @pytest.fixture
    def hedging_messages(self) -> list[MagicMock]:
        """Create messages with hedging patterns."""
        patterns = [
            "I suppose we could try that approach",
            "maybe we should wait until tomorrow",
            "probably around 3pm",
            "Like a week or so",
            "I think its ready",
            "I guess that works",
            "might be faster to just call",
            "could be the network",
            "ish, give or take 10 mins",
            "not sure but I think so",
        ]
        messages = []
        for i, text in enumerate(patterns):
            msg = MagicMock()
            msg.text = text
            msg.date = f"2025-12-{10 + i}T10:00:00+00:00"
            msg.is_outgoing = True
            messages.append(msg)
        return messages

    def test_extracts_hedging_patterns(
        self, hedging_messages: list[MagicMock]
    ) -> None:
        """analyze_patterns extracts hedging patterns from sample messages."""
        analyzer = StyleAnalyzer()
        result = analyzer.analyze_patterns(hedging_messages)

        hedging = result.hedging
        assert hedging.name == "Hedging"
        assert len(hedging.patterns) > 0

        # Check that key patterns are found
        pattern_names = {p.pattern for p in hedging.patterns}
        # At least some of these should be detected
        expected_patterns = {"I suppose", "maybe", "probably", "I think", "I guess", "might", "not sure"}
        found = pattern_names & expected_patterns
        assert len(found) >= 3, f"Expected at least 3 hedging patterns, found: {found}"


class TestSeanMdGeneration:
    """Test that SEAN.md generator produces required sections."""

    @pytest.fixture
    def sample_messages(self) -> list[MagicMock]:
        """Create sample messages for analysis."""
        texts = [
            "I suppose we could try that",
            "Yep, sounds good",
            "Mk let me check",
            "maybe tomorrow?",
            "one sec, brb",
            "ok so where were we",
            "wait, I meant the other one",
            "can you check on that please",
            "just checking in on the hotel",
            "cool thanks!",
        ]
        messages = []
        for i, text in enumerate(texts):
            msg = MagicMock()
            msg.text = text
            msg.date = f"2025-12-{10 + i}T10:00:00+00:00"
            msg.is_outgoing = True
            messages.append(msg)
        return messages

    def test_generates_all_required_sections(
        self, sample_messages: list[MagicMock]
    ) -> None:
        """SEAN.md contains all required sections."""
        analyzer = StyleAnalyzer()
        result = analyzer.analyze_patterns(sample_messages)
        md = analyzer.generate_sean_md(result)

        # Check all required sections exist
        required_sections = [
            "# SEAN.md",
            "## Executive Summary",
            "## Core Communication Patterns",
            "## Anti-Patterns",
            "Do NOT use emojis",
            "Do NOT use markdown",
            "Do NOT use verbose confirmations",
            "## Sample Transformations",
            "## Implementation Guidelines",
        ]

        for section in required_sections:
            assert section in md, f"Missing required section: {section}"

    def test_includes_pattern_examples(
        self, sample_messages: list[MagicMock]
    ) -> None:
        """SEAN.md includes examples from analyzed messages."""
        analyzer = StyleAnalyzer()
        result = analyzer.analyze_patterns(sample_messages)
        md = analyzer.generate_sean_md(result)

        # Should include some actual quotes from messages
        assert "### Hedging" in md or "### Acknowledgment" in md


class TestSeanVoicePersonality:
    """Test that sean-voice personality loads and formats correctly."""

    @pytest.fixture
    def personality_loader(self) -> PersonalityLoader:
        """Get a personality loader."""
        return PersonalityLoader()

    def test_sean_voice_personality_exists(
        self, personality_loader: PersonalityLoader
    ) -> None:
        """sean-voice personality file exists and loads."""
        personality = personality_loader.get("sean-voice")

        assert personality is not None
        assert personality.id == "sean-voice"
        assert personality.name == "Sean's Voice"

    def test_sean_voice_traits_correct(
        self, personality_loader: PersonalityLoader
    ) -> None:
        """sean-voice has correct communication traits."""
        personality = personality_loader.get("sean-voice")
        assert personality is not None

        cs = personality.traits.communication_style
        assert cs.tone == "casual"
        assert cs.verbosity == "very_concise"
        assert cs.emoji_usage == "never"

    def test_sean_voice_guidelines_present(
        self, personality_loader: PersonalityLoader
    ) -> None:
        """sean-voice has guidelines for message generation."""
        personality = personality_loader.get("sean-voice")
        assert personality is not None

        guidelines = personality.system_prompt_additions.guidelines
        assert len(guidelines) > 0

        # Check for key guidelines
        guideline_text = " ".join(guidelines).lower()
        assert "emoji" in guideline_text
        assert "short" in guideline_text or "brief" in guideline_text

    def test_sean_voice_examples_present(
        self, personality_loader: PersonalityLoader
    ) -> None:
        """sean-voice has example responses."""
        personality = personality_loader.get("sean-voice")
        assert personality is not None

        examples = personality.system_prompt_additions.examples
        assert len(examples) >= 5

        # Check that examples are brief
        for ex in examples:
            response = ex.get("response", "")
            assert len(response) < 100, f"Example too long: {response}"

    def test_sean_voice_format_for_prompt(
        self, personality_loader: PersonalityLoader
    ) -> None:
        """sean-voice formats correctly for prompts."""
        personality = personality_loader.get("sean-voice")
        assert personality is not None

        prompt_section = personality.format_for_prompt()

        assert "Sean's Voice" in prompt_section
        assert "casual" in prompt_section
        assert "very_concise" in prompt_section


class TestJorbsUsingSeanVoice:
    """Test that jorbs can use sean-voice personality."""

    @pytest.mark.asyncio
    async def test_jorb_session_with_sean_voice(self) -> None:
        """JorbSession can be created with sean-voice personality."""
        from services.jorb_storage import Jorb, JorbWithMessages

        # Create a test jorb with sean-voice personality
        jorb = Jorb(
            id="jorb_test123",
            name="Test Jorb",
            status="running",
            original_plan="Test plan",
            personality="sean-voice",
        )
        jorb_with_messages = JorbWithMessages(jorb=jorb, messages=[])

        # Create jorb session
        from services.jorb_session import create_jorb_session

        session = create_jorb_session(
            jorb_with_messages,
            policy={},
        )

        # Verify personality is loaded
        assert session._personality is not None
        assert session._personality.id == "sean-voice"

    @pytest.mark.asyncio
    async def test_sean_voice_produces_informal_messages(self) -> None:
        """Sean-voice personality produces informal, concise messages."""
        # This is a mock test since we can't actually call OpenAI
        from services.jorb_session import JorbSession
        from services.jorb_storage import Jorb, JorbWithMessages
        from services.personality_loader import get_personality_loader

        jorb = Jorb(
            id="jorb_test456",
            name="Test Jorb",
            status="running",
            original_plan="Confirm hotel booking",
            personality="sean-voice",
        )
        jorb_with_messages = JorbWithMessages(jorb=jorb, messages=[])

        personality = get_personality_loader().get("sean-voice")
        assert personality is not None

        # Check that the personality would produce appropriate messages
        prompt = personality.format_for_prompt()

        # Verify key constraints are in the prompt
        assert "NEVER use emojis" in prompt or "emoji" in prompt.lower()
        assert "short" in prompt.lower() or "brief" in prompt.lower() or "concise" in prompt.lower()


class TestEndToEndStyleCapture:
    """End-to-end test of the complete style capture flow."""

    @pytest.mark.asyncio
    async def test_full_flow_dry_run(self) -> None:
        """Complete flow from fetch to generation (dry run)."""
        from actions.style_capture import generate_sean_md_action

        # Create mock messages
        mock_messages = []
        texts = [
            "I suppose we should check first",
            "Yep sounds good",
            "one sec brb",
            "cool thanks",
        ]
        for i, text in enumerate(texts):
            msg = MagicMock()
            msg.text = text
            msg.date = f"2025-12-{10 + i}T10:00:00+00:00"
            msg.is_outgoing = True
            mock_messages.append(msg)

        # Mock telegram service
        mock_telegram = MagicMock()
        mock_telegram.is_configured = True
        mock_telegram.get_all_messages = AsyncMock(return_value=mock_messages)

        with patch(
            "actions.style_capture.TelegramClientService",
            return_value=mock_telegram,
        ):
            result = await generate_sean_md_action({
                "chat_id": "@TestChat",
                "dry_run": "true",
            })

        assert result["success"] is True
        assert result["messages_analyzed"] == 4
        assert result["dry_run"] is True
        assert "preview" in result
        assert "SEAN.md" in result["preview"]
