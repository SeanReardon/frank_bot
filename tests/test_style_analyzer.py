"""
Unit tests for StyleAnalyzer.

Tests verify pattern extraction and analysis functionality.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from services.style_analyzer import (
    StyleAnalyzer,
    StyleAnalysisResult,
    PatternCategory,
    PatternExample,
)


class TestPatternCategory:
    """Tests for PatternCategory dataclass."""

    def test_add_example(self) -> None:
        """add_example adds PatternExample to patterns list."""
        category = PatternCategory(name="Test", description="Test category")
        category.add_example("pattern1", "quote1", "context1")

        assert len(category.patterns) == 1
        assert category.patterns[0].pattern == "pattern1"
        assert category.patterns[0].quote == "quote1"
        assert category.patterns[0].context == "context1"

    def test_add_example_without_context(self) -> None:
        """add_example works without context."""
        category = PatternCategory(name="Test", description="Test category")
        category.add_example("pattern1", "quote1")

        assert len(category.patterns) == 1
        assert category.patterns[0].context is None


class TestStyleAnalyzer:
    """Tests for StyleAnalyzer class."""

    @pytest.fixture
    def analyzer(self) -> StyleAnalyzer:
        """Create a StyleAnalyzer instance."""
        return StyleAnalyzer()

    @pytest.fixture
    def sample_messages(self) -> list[MagicMock]:
        """Create sample messages for analysis."""
        messages = []
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
        for i, text in enumerate(texts):
            msg = MagicMock()
            msg.text = text
            msg.date = f"2025-12-{10 + i}T10:00:00+00:00"
            msg.is_outgoing = True
            messages.append(msg)
        return messages

    def test_analyze_patterns_returns_result(
        self, analyzer: StyleAnalyzer, sample_messages: list[MagicMock]
    ) -> None:
        """analyze_patterns returns StyleAnalysisResult."""
        result = analyzer.analyze_patterns(sample_messages)

        assert isinstance(result, StyleAnalysisResult)
        assert result.total_messages_analyzed == 10

    def test_analyze_patterns_extracts_hedging(
        self, analyzer: StyleAnalyzer, sample_messages: list[MagicMock]
    ) -> None:
        """analyze_patterns extracts hedging patterns."""
        result = analyzer.analyze_patterns(sample_messages)

        assert result.hedging.name == "Hedging"
        patterns = [p.pattern for p in result.hedging.patterns]
        assert "I suppose" in patterns or "maybe" in patterns

    def test_analyze_patterns_extracts_acknowledgment(
        self, analyzer: StyleAnalyzer, sample_messages: list[MagicMock]
    ) -> None:
        """analyze_patterns extracts acknowledgment patterns."""
        result = analyzer.analyze_patterns(sample_messages)

        assert result.acknowledgment.name == "Acknowledgment"
        patterns = [p.pattern for p in result.acknowledgment.patterns]
        assert "Yep" in patterns or "Mk" in patterns or "cool" in patterns

    def test_analyze_patterns_extracts_pausing(
        self, analyzer: StyleAnalyzer, sample_messages: list[MagicMock]
    ) -> None:
        """analyze_patterns extracts pausing patterns."""
        result = analyzer.analyze_patterns(sample_messages)

        patterns = [p.pattern for p in result.pausing.patterns]
        assert "one sec" in patterns or "brb" in patterns

    def test_analyze_patterns_extracts_revision(
        self, analyzer: StyleAnalyzer, sample_messages: list[MagicMock]
    ) -> None:
        """analyze_patterns extracts revision patterns."""
        result = analyzer.analyze_patterns(sample_messages)

        patterns = [p.pattern for p in result.revision.patterns]
        assert "wait" in patterns or "I meant" in patterns

    def test_analyze_patterns_extracts_action_requests(
        self, analyzer: StyleAnalyzer, sample_messages: list[MagicMock]
    ) -> None:
        """analyze_patterns extracts action request patterns."""
        result = analyzer.analyze_patterns(sample_messages)

        patterns = [p.pattern for p in result.action_requests.patterns]
        assert "can you" in patterns or "please" in patterns

    def test_analyze_patterns_extracts_follow_ups(
        self, analyzer: StyleAnalyzer, sample_messages: list[MagicMock]
    ) -> None:
        """analyze_patterns extracts follow-up patterns."""
        result = analyzer.analyze_patterns(sample_messages)

        patterns = [p.pattern for p in result.follow_ups.patterns]
        assert "just checking" in patterns

    def test_analyze_patterns_handles_empty_messages(
        self, analyzer: StyleAnalyzer
    ) -> None:
        """analyze_patterns handles empty message list."""
        result = analyzer.analyze_patterns([])

        assert result.total_messages_analyzed == 0
        assert result.date_range_start is None
        assert result.date_range_end is None

    def test_analyze_patterns_handles_none_text(
        self, analyzer: StyleAnalyzer
    ) -> None:
        """analyze_patterns skips messages with None text."""
        msg = MagicMock()
        msg.text = None
        msg.date = "2025-12-15T10:00:00+00:00"

        result = analyzer.analyze_patterns([msg])

        assert result.total_messages_analyzed == 1
        # No patterns should be extracted
        assert len(result.hedging.patterns) == 0

    def test_all_categories_returns_all(
        self, analyzer: StyleAnalyzer, sample_messages: list[MagicMock]
    ) -> None:
        """all_categories returns all pattern categories."""
        result = analyzer.analyze_patterns(sample_messages)

        categories = result.all_categories()
        assert len(categories) == 9
        names = [c.name for c in categories]
        assert "Hedging" in names
        assert "Acknowledgment" in names
        assert "Tone Markers" in names

    def test_analyze_tone_markers_lowercase(
        self, analyzer: StyleAnalyzer
    ) -> None:
        """analyze_patterns detects lowercase preference."""
        msg = MagicMock()
        msg.text = "sounds good to me"
        msg.date = "2025-12-15T10:00:00+00:00"

        result = analyzer.analyze_patterns([msg])

        # Should have lowercase pattern in tone markers
        patterns = [p.pattern for p in result.tone_markers.patterns]
        assert "Lowercase preference" in patterns

    def test_analyze_limits_examples_per_pattern(
        self, analyzer: StyleAnalyzer
    ) -> None:
        """analyze_patterns limits to 5 examples per pattern type."""
        messages = []
        for i in range(10):
            msg = MagicMock()
            msg.text = f"Yep {i} sounds good"
            msg.date = f"2025-12-{10 + i}T10:00:00+00:00"
            messages.append(msg)

        result = analyzer.analyze_patterns(messages)

        yep_patterns = [p for p in result.acknowledgment.patterns if p.pattern == "Yep"]
        assert len(yep_patterns) <= 5


class TestStyleAnalyzerFetch:
    """Tests for fetch_authentic_messages method."""

    @pytest.fixture
    def mock_telegram(self) -> MagicMock:
        """Create mock TelegramClientService."""
        mock = MagicMock()
        mock.get_all_messages = AsyncMock(return_value=[])
        return mock

    @pytest.mark.asyncio
    async def test_fetch_authentic_messages_calls_telegram(
        self, mock_telegram: MagicMock
    ) -> None:
        """fetch_authentic_messages calls telegram service correctly."""
        analyzer = StyleAnalyzer(telegram_service=mock_telegram)
        before_date = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        await analyzer.fetch_authentic_messages("@MagicConciergeBot", before_date)

        mock_telegram.get_all_messages.assert_called_once_with(
            chat_id="@MagicConciergeBot",
            before_date=before_date,
            direction_filter="outgoing",
        )

    @pytest.mark.asyncio
    async def test_fetch_authentic_messages_default_date(
        self, mock_telegram: MagicMock
    ) -> None:
        """fetch_authentic_messages defaults to 2026-01-01."""
        analyzer = StyleAnalyzer(telegram_service=mock_telegram)

        await analyzer.fetch_authentic_messages("@MagicConciergeBot")

        call_args = mock_telegram.get_all_messages.call_args
        before_date = call_args.kwargs["before_date"]
        assert before_date.year == 2026
        assert before_date.month == 1
        assert before_date.day == 1

    @pytest.mark.asyncio
    async def test_fetch_creates_service_if_not_provided(self) -> None:
        """fetch_authentic_messages creates TelegramClientService if not provided."""
        analyzer = StyleAnalyzer()

        with patch("services.telegram_client.TelegramClientService") as mock_cls:
            mock_service = MagicMock()
            mock_service.get_all_messages = AsyncMock(return_value=[])
            mock_cls.return_value = mock_service

            await analyzer.fetch_authentic_messages("@testuser")

            mock_cls.assert_called_once()
            mock_service.get_all_messages.assert_called_once()


class TestGenerateSeanMd:
    """Tests for generate_sean_md method."""

    @pytest.fixture
    def analyzer(self) -> StyleAnalyzer:
        """Create a StyleAnalyzer instance."""
        return StyleAnalyzer()

    @pytest.fixture
    def sample_messages(self) -> list[MagicMock]:
        """Create sample messages for analysis."""
        messages = []
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
        for i, text in enumerate(texts):
            msg = MagicMock()
            msg.text = text
            msg.date = f"2025-12-{10 + i}T10:00:00+00:00"
            msg.is_outgoing = True
            messages.append(msg)
        return messages

    def test_generate_returns_string(
        self, analyzer: StyleAnalyzer, sample_messages: list[MagicMock]
    ) -> None:
        """generate_sean_md returns a string."""
        result = analyzer.analyze_patterns(sample_messages)
        md = analyzer.generate_sean_md(result)

        assert isinstance(md, str)
        assert len(md) > 0

    def test_generate_includes_title(
        self, analyzer: StyleAnalyzer, sample_messages: list[MagicMock]
    ) -> None:
        """generate_sean_md includes title."""
        result = analyzer.analyze_patterns(sample_messages)
        md = analyzer.generate_sean_md(result)

        assert "# SEAN.md" in md

    def test_generate_includes_executive_summary(
        self, analyzer: StyleAnalyzer, sample_messages: list[MagicMock]
    ) -> None:
        """generate_sean_md includes executive summary."""
        result = analyzer.analyze_patterns(sample_messages)
        md = analyzer.generate_sean_md(result)

        assert "## Executive Summary" in md
        assert "brevity" in md.lower()

    def test_generate_includes_pattern_sections(
        self, analyzer: StyleAnalyzer, sample_messages: list[MagicMock]
    ) -> None:
        """generate_sean_md includes pattern sections."""
        result = analyzer.analyze_patterns(sample_messages)
        md = analyzer.generate_sean_md(result)

        assert "### Hedging" in md
        assert "### Acknowledgment" in md
        assert "### Pausing" in md

    def test_generate_includes_anti_patterns(
        self, analyzer: StyleAnalyzer, sample_messages: list[MagicMock]
    ) -> None:
        """generate_sean_md includes anti-patterns section."""
        result = analyzer.analyze_patterns(sample_messages)
        md = analyzer.generate_sean_md(result)

        assert "## Anti-Patterns" in md
        assert "Do NOT use emojis" in md
        assert "Do NOT use markdown" in md
        assert "Do NOT use verbose confirmations" in md

    def test_generate_includes_transformations(
        self, analyzer: StyleAnalyzer, sample_messages: list[MagicMock]
    ) -> None:
        """generate_sean_md includes sample transformations."""
        result = analyzer.analyze_patterns(sample_messages)
        md = analyzer.generate_sean_md(result)

        assert "## Sample Transformations" in md
        assert "**Formal:**" in md
        assert "**Sean:**" in md

    def test_generate_includes_implementation_guidelines(
        self, analyzer: StyleAnalyzer, sample_messages: list[MagicMock]
    ) -> None:
        """generate_sean_md includes implementation guidelines."""
        result = analyzer.analyze_patterns(sample_messages)
        md = analyzer.generate_sean_md(result)

        assert "## Implementation Guidelines" in md
        assert "Keep it short" in md

    def test_generate_includes_message_count(
        self, analyzer: StyleAnalyzer, sample_messages: list[MagicMock]
    ) -> None:
        """generate_sean_md includes message count."""
        result = analyzer.analyze_patterns(sample_messages)
        md = analyzer.generate_sean_md(result)

        assert "**Messages analyzed**: 10" in md

    def test_generate_handles_empty_analysis(
        self, analyzer: StyleAnalyzer
    ) -> None:
        """generate_sean_md handles empty analysis result."""
        result = analyzer.analyze_patterns([])
        md = analyzer.generate_sean_md(result)

        assert isinstance(md, str)
        assert "# SEAN.md" in md
        assert "**Messages analyzed**: 0" in md
