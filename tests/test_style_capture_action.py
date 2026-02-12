"""
Unit tests for style_capture action.

Tests verify SEAN.md generation and Telegram delivery.
"""

from __future__ import annotations

from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from actions.style_capture import (
    generate_sean_md_action,
    _split_message,
    TELEGRAM_MESSAGE_LIMIT,
)


class TestSplitMessage:
    """Tests for _split_message helper."""

    def test_short_message_unchanged(self) -> None:
        """Messages under limit are returned as-is."""
        content = "Short message"
        chunks = _split_message(content)

        assert len(chunks) == 1
        assert chunks[0] == content

    def test_long_message_split_at_paragraphs(self) -> None:
        """Long messages split at paragraph boundaries."""
        para1 = "First paragraph." * 100
        para2 = "Second paragraph." * 100
        content = f"{para1}\n\n{para2}"

        chunks = _split_message(content, limit=2000)

        assert len(chunks) >= 2
        # First chunk should contain first paragraph
        assert "First paragraph" in chunks[0]

    def test_very_long_line_hard_split(self) -> None:
        """Very long single lines are hard split."""
        content = "x" * 10000
        chunks = _split_message(content, limit=1000)

        assert len(chunks) >= 10
        for chunk in chunks:
            assert len(chunk) <= 1000

    def test_preserves_all_content(self) -> None:
        """All content is preserved after splitting."""
        content = "A" * 5000 + "\n\n" + "B" * 5000
        chunks = _split_message(content, limit=2000)

        combined = "\n\n".join(chunks)
        # Should have all original characters (minus some joining whitespace)
        assert combined.count("A") == 5000
        assert combined.count("B") == 5000


class TestGenerateSeanMdAction:
    """Tests for generate_sean_md_action."""

    @pytest.fixture
    def mock_telegram(self) -> MagicMock:
        """Create mock TelegramClientService."""
        mock = MagicMock()
        mock.is_configured = True
        mock.send_message = AsyncMock(
            return_value=MagicMock(success=True, message_id=123)
        )
        return mock

    @pytest.fixture
    def mock_bot(self) -> MagicMock:
        """Create mock TelegramBot."""
        mock = MagicMock()
        mock.is_configured = True
        mock.chat_id = "123456"
        mock.send_notification = AsyncMock(
            return_value=MagicMock(success=True, message_id=123)
        )
        return mock

    @pytest.fixture
    def mock_analyzer(self) -> MagicMock:
        """Create mock StyleAnalyzer."""
        mock = MagicMock()

        # Create a mock analysis result
        mock_result = MagicMock()
        mock_result.total_messages_analyzed = 100
        mock_result.date_range_start = "2025-01-01T00:00:00+00:00"
        mock_result.date_range_end = "2025-12-31T23:59:59+00:00"
        mock_result.all_categories.return_value = [
            MagicMock(name="Hedging", patterns=[]),
            MagicMock(name="Acknowledgment", patterns=[]),
        ]

        mock.fetch_authentic_messages = AsyncMock(
            return_value=[MagicMock(text="test", date="2025-12-15T10:00:00+00:00")]
        )
        mock.analyze_patterns.return_value = mock_result
        mock.generate_sean_md.return_value = "# SEAN.md\n\nTest content"

        return mock

    @pytest.mark.asyncio
    async def test_action_requires_telegram_config(self) -> None:
        """Action raises error if Telegram not configured."""
        with patch(
            "actions.style_capture.TelegramClientService"
        ) as mock_cls:
            mock_service = MagicMock()
            mock_service.is_configured = False
            mock_cls.return_value = mock_service

            with pytest.raises(ValueError, match="not configured"):
                await generate_sean_md_action({})

    @pytest.mark.asyncio
    async def test_action_fetches_messages(
        self, mock_telegram: MagicMock, mock_analyzer: MagicMock
    ) -> None:
        """Action fetches messages from specified chat."""
        with patch(
            "actions.style_capture.TelegramClientService",
            return_value=mock_telegram,
        ):
            with patch(
                "actions.style_capture.StyleAnalyzer",
                return_value=mock_analyzer,
            ):
                result = await generate_sean_md_action(
                    {"chat_id": "@TestChat", "dry_run": "true"}
                )

                mock_analyzer.fetch_authentic_messages.assert_called_once()
                call_args = mock_analyzer.fetch_authentic_messages.call_args
                assert call_args.kwargs["chat_id"] == "@TestChat"

    @pytest.mark.asyncio
    async def test_action_analyzes_and_generates(
        self, mock_telegram: MagicMock, mock_analyzer: MagicMock
    ) -> None:
        """Action calls analyze_patterns and generate_sean_md."""
        with patch(
            "actions.style_capture.TelegramClientService",
            return_value=mock_telegram,
        ):
            with patch(
                "actions.style_capture.StyleAnalyzer",
                return_value=mock_analyzer,
            ):
                result = await generate_sean_md_action({"dry_run": "true"})

                mock_analyzer.analyze_patterns.assert_called_once()
                mock_analyzer.generate_sean_md.assert_called_once()

    @pytest.mark.asyncio
    async def test_action_sends_to_recipient(
        self, mock_telegram: MagicMock, mock_bot: MagicMock, mock_analyzer: MagicMock
    ) -> None:
        """Action sends content to recipient when not dry_run."""
        with patch(
            "actions.style_capture.TelegramClientService",
            return_value=mock_telegram,
        ):
            with patch(
                "actions.style_capture.TelegramBot",
                return_value=mock_bot,
            ):
                with patch(
                    "actions.style_capture.StyleAnalyzer",
                    return_value=mock_analyzer,
                ):
                    result = await generate_sean_md_action(
                        {"recipient": "@TestUser", "dry_run": "false"}
                    )

                    mock_bot.send_notification.assert_called()
                    call_args = mock_bot.send_notification.call_args
                    assert call_args.kwargs["chat_id"] == "@TestUser"
                    assert result["recipient"] == "@TestUser"

    @pytest.mark.asyncio
    async def test_action_dry_run_skips_send(
        self, mock_telegram: MagicMock, mock_analyzer: MagicMock
    ) -> None:
        """Action skips sending when dry_run is true."""
        with patch(
            "actions.style_capture.TelegramClientService",
            return_value=mock_telegram,
        ):
            with patch(
                "actions.style_capture.StyleAnalyzer",
                return_value=mock_analyzer,
            ):
                result = await generate_sean_md_action({"dry_run": "true"})

                mock_telegram.send_message.assert_not_called()
                assert result["dry_run"] is True
                assert result["message_count"] == 0

    @pytest.mark.asyncio
    async def test_action_splits_long_content(
        self, mock_telegram: MagicMock, mock_bot: MagicMock, mock_analyzer: MagicMock
    ) -> None:
        """Action splits content exceeding Telegram limit."""
        # Generate content that exceeds limit
        mock_analyzer.generate_sean_md.return_value = "X" * 10000

        with patch(
            "actions.style_capture.TelegramClientService",
            return_value=mock_telegram,
        ):
            with patch(
                "actions.style_capture.TelegramBot",
                return_value=mock_bot,
            ):
                with patch(
                    "actions.style_capture.StyleAnalyzer",
                    return_value=mock_analyzer,
                ):
                    result = await generate_sean_md_action({"dry_run": "false"})

                    # Should have multiple sends
                    assert mock_bot.send_notification.call_count >= 2
                    assert result["message_count"] >= 2

    @pytest.mark.asyncio
    async def test_action_returns_success_response(
        self, mock_telegram: MagicMock, mock_analyzer: MagicMock
    ) -> None:
        """Action returns proper success response."""
        with patch(
            "actions.style_capture.TelegramClientService",
            return_value=mock_telegram,
        ):
            with patch(
                "actions.style_capture.StyleAnalyzer",
                return_value=mock_analyzer,
            ):
                result = await generate_sean_md_action({"dry_run": "true"})

                assert result["success"] is True
                assert result["messages_analyzed"] == 100
                assert "preview" in result
                assert "patterns_found" in result

    @pytest.mark.asyncio
    async def test_action_handles_no_messages(
        self, mock_telegram: MagicMock, mock_analyzer: MagicMock
    ) -> None:
        """Action raises error when no messages found."""
        mock_analyzer.fetch_authentic_messages = AsyncMock(return_value=[])

        with patch(
            "actions.style_capture.TelegramClientService",
            return_value=mock_telegram,
        ):
            with patch(
                "actions.style_capture.StyleAnalyzer",
                return_value=mock_analyzer,
            ):
                with pytest.raises(ValueError, match="No outgoing messages"):
                    await generate_sean_md_action({})

    @pytest.mark.asyncio
    async def test_action_handles_send_failure(
        self, mock_telegram: MagicMock, mock_bot: MagicMock, mock_analyzer: MagicMock
    ) -> None:
        """Action raises error when send fails."""
        mock_bot.send_notification = AsyncMock(
            return_value=MagicMock(success=False, error="Rate limited")
        )

        with patch(
            "actions.style_capture.TelegramClientService",
            return_value=mock_telegram,
        ):
            with patch(
                "actions.style_capture.TelegramBot",
                return_value=mock_bot,
            ):
                with patch(
                    "actions.style_capture.StyleAnalyzer",
                    return_value=mock_analyzer,
                ):
                    with pytest.raises(ValueError, match="Failed to send"):
                        await generate_sean_md_action({"dry_run": "false"})

    @pytest.mark.asyncio
    async def test_action_parses_before_date_iso(
        self, mock_telegram: MagicMock, mock_analyzer: MagicMock
    ) -> None:
        """Action parses ISO format before_date."""
        with patch(
            "actions.style_capture.TelegramClientService",
            return_value=mock_telegram,
        ):
            with patch(
                "actions.style_capture.StyleAnalyzer",
                return_value=mock_analyzer,
            ):
                result = await generate_sean_md_action(
                    {"before_date": "2025-06-15T12:00:00Z", "dry_run": "true"}
                )

                call_args = mock_analyzer.fetch_authentic_messages.call_args
                before_date = call_args.kwargs.get("before_date")
                assert before_date.year == 2025
                assert before_date.month == 6
                assert before_date.day == 15

    @pytest.mark.asyncio
    async def test_action_parses_before_date_simple(
        self, mock_telegram: MagicMock, mock_analyzer: MagicMock
    ) -> None:
        """Action parses simple date format before_date."""
        with patch(
            "actions.style_capture.TelegramClientService",
            return_value=mock_telegram,
        ):
            with patch(
                "actions.style_capture.StyleAnalyzer",
                return_value=mock_analyzer,
            ):
                result = await generate_sean_md_action(
                    {"before_date": "2025-06-15", "dry_run": "true"}
                )

                call_args = mock_analyzer.fetch_authentic_messages.call_args
                before_date = call_args.kwargs.get("before_date")
                assert before_date.year == 2025
                assert before_date.month == 6

    @pytest.mark.asyncio
    async def test_action_invalid_before_date_raises(
        self, mock_telegram: MagicMock
    ) -> None:
        """Action raises error for invalid before_date."""
        with patch(
            "actions.style_capture.TelegramClientService",
            return_value=mock_telegram,
        ):
            with pytest.raises(ValueError, match="Invalid before_date"):
                await generate_sean_md_action({"before_date": "not-a-date"})

    @pytest.mark.asyncio
    async def test_action_uses_default_chat_id(
        self, mock_telegram: MagicMock, mock_analyzer: MagicMock
    ) -> None:
        """Action uses @MagicConciergeBot as default chat_id."""
        with patch(
            "actions.style_capture.TelegramClientService",
            return_value=mock_telegram,
        ):
            with patch(
                "actions.style_capture.StyleAnalyzer",
                return_value=mock_analyzer,
            ):
                await generate_sean_md_action({"dry_run": "true"})

                call_args = mock_analyzer.fetch_authentic_messages.call_args
                assert call_args.kwargs["chat_id"] == "@MagicConciergeBot"

    @pytest.mark.asyncio
    async def test_action_uses_default_recipient(
        self, mock_telegram: MagicMock, mock_bot: MagicMock, mock_analyzer: MagicMock
    ) -> None:
        """Action uses TelegramBot configured chat_id by default."""
        with patch(
            "actions.style_capture.TelegramClientService",
            return_value=mock_telegram,
        ):
            with patch(
                "actions.style_capture.TelegramBot",
                return_value=mock_bot,
            ):
                with patch(
                    "actions.style_capture.StyleAnalyzer",
                    return_value=mock_analyzer,
                ):
                    result = await generate_sean_md_action({"dry_run": "false"})

                    assert result["recipient"] == mock_bot.chat_id
