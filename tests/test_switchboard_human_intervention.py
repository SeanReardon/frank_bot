"""
Unit tests for Switchboard human intervention handling.

Tests verify that routing correctly handles the is_human_intervention flag
for Stream B (Sean's direct messages).
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from services.switchboard import Switchboard, RoutingDecision
from services.jorb_storage import Jorb, JorbContact, JorbWithMessages


class TestRoutingDecisionHumanIntervention:
    """Tests for RoutingDecision is_human_intervention field."""

    def test_routing_decision_defaults_no_human_intervention(self) -> None:
        """RoutingDecision defaults is_human_intervention to False."""
        decision = RoutingDecision(
            jorb_id="jorb_123",
            confidence="high",
            reasoning="Test",
        )
        assert decision.is_human_intervention is False

    def test_routing_decision_with_human_intervention(self) -> None:
        """RoutingDecision can have is_human_intervention=True."""
        decision = RoutingDecision(
            jorb_id="jorb_123",
            confidence="high",
            reasoning="Test",
            is_human_intervention=True,
        )
        assert decision.is_human_intervention is True


class TestSwitchboardRouteHumanIntervention:
    """Tests for Switchboard.route with is_human_intervention parameter."""

    @pytest.fixture
    def switchboard(self) -> Switchboard:
        """Create a Switchboard instance without API key (fast match only)."""
        return Switchboard(openai_api_key=None)

    @pytest.fixture
    def open_jorbs(self) -> list[JorbWithMessages]:
        """Create test jorbs."""
        jorb = Jorb(
            id="jorb_test1",
            name="Test Jorb",
            status="running",
            original_plan="Test plan",
        )
        jorb.contacts = [
            JorbContact(identifier="@TestContact", channel="telegram", name="Test"),
            JorbContact(identifier="+15551234567", channel="sms", name="SMS Contact"),
        ]
        return [JorbWithMessages(jorb=jorb, messages=[])]

    @pytest.mark.asyncio
    async def test_route_without_human_intervention(
        self, switchboard: Switchboard, open_jorbs: list[JorbWithMessages]
    ) -> None:
        """Normal routing sets is_human_intervention=False."""
        decision = await switchboard.route(
            channel="telegram",
            sender="@TestContact",
            sender_name="Test",
            content="Hello",
            timestamp=datetime.now(timezone.utc).isoformat(),
            open_jorbs=open_jorbs,
            is_human_intervention=False,
        )

        assert decision.jorb_id == "jorb_test1"
        assert decision.confidence == "high"
        assert decision.is_human_intervention is False

    @pytest.mark.asyncio
    async def test_route_with_human_intervention(
        self, switchboard: Switchboard, open_jorbs: list[JorbWithMessages]
    ) -> None:
        """Human intervention routing sets is_human_intervention=True."""
        decision = await switchboard.route(
            channel="telegram",
            sender="@TestContact",
            sender_name="Test",
            content="I'm taking over here",
            timestamp=datetime.now(timezone.utc).isoformat(),
            open_jorbs=open_jorbs,
            is_human_intervention=True,
        )

        assert decision.jorb_id == "jorb_test1"
        assert decision.confidence == "high"  # Sean knows what he's doing
        assert decision.is_human_intervention is True

    @pytest.mark.asyncio
    async def test_route_human_intervention_no_match(
        self, switchboard: Switchboard, open_jorbs: list[JorbWithMessages]
    ) -> None:
        """Human intervention with unknown contact still passes flag."""
        decision = await switchboard.route(
            channel="telegram",
            sender="@UnknownContact",
            sender_name="Unknown",
            content="Some message",
            timestamp=datetime.now(timezone.utc).isoformat(),
            open_jorbs=open_jorbs,
            is_human_intervention=True,
        )

        # No match (unknown contact and no LLM), but flag preserved
        assert decision.jorb_id is None
        assert decision.is_human_intervention is True

    @pytest.mark.asyncio
    async def test_route_fast_match_with_intervention(
        self, switchboard: Switchboard, open_jorbs: list[JorbWithMessages]
    ) -> None:
        """Fast contact match works with human intervention flag."""
        # Test with phone number normalization
        decision = await switchboard.route(
            channel="sms",
            sender="+1 (555) 123-4567",  # Different format
            sender_name=None,
            content="Quick update",
            timestamp=datetime.now(timezone.utc).isoformat(),
            open_jorbs=open_jorbs,
            is_human_intervention=True,
        )

        assert decision.jorb_id == "jorb_test1"
        assert decision.confidence == "high"
        assert decision.is_human_intervention is True

    @pytest.mark.asyncio
    async def test_route_logs_human_intervention(
        self, switchboard: Switchboard, open_jorbs: list[JorbWithMessages]
    ) -> None:
        """Routing logs when human intervention is detected."""
        with patch("services.switchboard.logger") as mock_logger:
            await switchboard.route(
                channel="telegram",
                sender="@TestContact",
                sender_name="Test",
                content="Taking over",
                timestamp=datetime.now(timezone.utc).isoformat(),
                open_jorbs=open_jorbs,
                is_human_intervention=True,
            )

            # Check that log message includes human intervention
            mock_logger.info.assert_called()
            call_args = mock_logger.info.call_args
            assert "human intervention" in str(call_args).lower()


class TestSwitchboardLLMRoutingWithIntervention:
    """Tests for LLM-based routing with human intervention."""

    @pytest.mark.asyncio
    async def test_llm_routing_high_confidence_for_intervention(self) -> None:
        """LLM routing returns high confidence when is_human_intervention and jorb matched."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """
        {
            "routing": {
                "jorb_id": "jorb_123",
                "confidence": "medium",
                "reasoning": "Content seems related"
            },
            "signals": {
                "might_be_new_jorb": false,
                "is_spam": false,
                "is_urgent": false,
                "unknown_sender": false
            }
        }
        """
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50

        with patch("services.switchboard.openai") as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.OpenAI.return_value = mock_client

            switchboard = Switchboard(openai_api_key="test-key")
            decision = await switchboard.route(
                channel="telegram",
                sender="@Unknown",
                sender_name=None,
                content="Test message",
                timestamp=datetime.now(timezone.utc).isoformat(),
                open_jorbs=[],
                is_human_intervention=True,
            )

            # Should override to high confidence because Sean knows what he's doing
            assert decision.jorb_id == "jorb_123"
            assert decision.confidence == "high"  # Upgraded from medium
            assert decision.is_human_intervention is True

    @pytest.mark.asyncio
    async def test_llm_routing_no_match_preserves_intervention(self) -> None:
        """LLM routing with no match still preserves is_human_intervention."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """
        {
            "routing": {
                "jorb_id": null,
                "confidence": "low",
                "reasoning": "No matching jorb found"
            },
            "signals": {
                "might_be_new_jorb": true,
                "is_spam": false,
                "is_urgent": false,
                "unknown_sender": true
            }
        }
        """
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50

        with patch("services.switchboard.openai") as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.OpenAI.return_value = mock_client

            switchboard = Switchboard(openai_api_key="test-key")
            decision = await switchboard.route(
                channel="telegram",
                sender="@Unknown",
                sender_name=None,
                content="Test message",
                timestamp=datetime.now(timezone.utc).isoformat(),
                open_jorbs=[],
                is_human_intervention=True,
            )

            assert decision.jorb_id is None
            assert decision.is_human_intervention is True
            assert decision.might_be_new_jorb is True
