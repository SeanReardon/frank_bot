"""
Tests for Switchboard behavior with channel='telegram_bot'.

Verifies that:
- telegram_bot channel is treated identically to telegram for routing
- Unmatched messages from trusted senders create catch-up jorbs
- Auto-create works for allowlisted bot senders
- Existing telegram/sms channel behavior is unchanged
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.agent_runner import AgentRunner, IncomingEvent


@pytest.fixture
def mock_storage():
    """Create a mock JorbStorage with basic stubs."""
    storage = MagicMock()
    storage.get_open_jorbs_with_messages = AsyncMock(return_value=[])
    storage.list_jorbs = AsyncMock(return_value=[])
    storage.create_jorb = AsyncMock()
    storage.update_jorb = AsyncMock()
    storage.add_message = AsyncMock()
    return storage


@pytest.fixture
def runner(mock_storage):
    """Create an AgentRunner with mocked deps."""
    with patch("services.agent_runner.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            openai_api_key="test-key",
            agent_spend_limit=100.0,
        )
        return AgentRunner(
            storage=mock_storage,
            openai_api_key="test-key",
        )


@pytest.fixture(autouse=True)
def enable_switchboard_mode(monkeypatch):
    """Re-enable switchboard mode for these tests (conftest disables it globally)."""
    monkeypatch.setenv("USE_SWITCHBOARD_MODE", "true")


class TestSwitchboardTelegramBotChannel:
    """Test that telegram_bot channel works with the Switchboard."""

    @pytest.mark.asyncio
    async def test_telegram_bot_autocreate_for_allowlisted_sender(self, runner):
        """telegram_bot from allowlisted sender with might_be_new_jorb creates a new jorb."""
        event = IncomingEvent(
            channel="telegram_bot",
            sender="@alloweduser",
            sender_name="Allowed User",
            content="Can you check my calendar for tomorrow?",
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata={
                "source": "telegram_bot",
                "telegram_bot_chat_id": "12345",
            },
        )

        # Mock switchboard: no match, might_be_new_jorb=True
        mock_routing = MagicMock(
            jorb_id=None,
            confidence="low",
            reasoning="No match found",
            might_be_new_jorb=True,
            is_spam=False,
            is_urgent=False,
            unknown_sender=False,
            is_human_intervention=False,
            tokens_used=100,
        )
        mock_switchboard = MagicMock()
        mock_switchboard.route = AsyncMock(return_value=mock_routing)

        with patch(
            "services.agent_runner.get_switchboard",
            return_value=mock_switchboard,
        ), patch(
            "services.telegram_allowlist.is_allowed_username",
            return_value=True,
        ), patch.object(
            runner,
            "_enrich_event_with_contact",
            new_callable=AsyncMock,
            side_effect=lambda e: e,
        ), patch.object(
            runner,
            "get_open_jorbs",
            new_callable=AsyncMock,
            return_value=[],
        ), patch.object(
            runner,
            "_create_new_jorb_from_event",
            new_callable=AsyncMock,
            return_value=MagicMock(
                jorb_id="jorb_new_1",
                action_taken="jorb_created",
                success=True,
            ),
        ) as mock_create:
            result = await runner.process_incoming_message(event)

            mock_create.assert_called_once()
            created_event = mock_create.call_args[0][0]
            assert created_event.channel == "telegram_bot"

    @pytest.mark.asyncio
    async def test_telegram_bot_catch_up_for_trusted_sender_no_match(self, runner):
        """telegram_bot from trusted sender with no match creates catch-up jorb."""
        event = IncomingEvent(
            channel="telegram_bot",
            sender="@trusteduser",
            sender_name="Trusted User",
            content="What about that hotel booking?",
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata={
                "source": "telegram_bot",
                "telegram_bot_chat_id": "99999",
            },
        )

        # Mock switchboard: no match, not new jorb
        mock_routing = MagicMock(
            jorb_id=None,
            confidence="low",
            reasoning="Unknown context",
            might_be_new_jorb=False,
            is_spam=False,
            is_urgent=False,
            unknown_sender=False,
            is_human_intervention=False,
            tokens_used=100,
        )
        mock_switchboard = MagicMock()
        mock_switchboard.route = AsyncMock(return_value=mock_routing)

        with patch(
            "services.agent_runner.get_switchboard",
            return_value=mock_switchboard,
        ), patch.object(
            runner,
            "_enrich_event_with_contact",
            new_callable=AsyncMock,
            side_effect=lambda e: e,
        ), patch.object(
            runner,
            "get_open_jorbs",
            new_callable=AsyncMock,
            return_value=[],
        ), patch.object(
            runner,
            "is_trusted_sender",
            new_callable=AsyncMock,
            return_value=True,
        ), patch.object(
            runner,
            "_create_catch_up_jorb",
            new_callable=AsyncMock,
            return_value=MagicMock(
                jorb_id="jorb_catchup_1",
                action_taken="catch_up_created",
                success=True,
            ),
        ) as mock_catch_up:
            result = await runner.process_incoming_message(event)

            assert result.action_taken == "catch_up_created"
            mock_catch_up.assert_called_once()
            catch_up_event = mock_catch_up.call_args[0][0]
            assert catch_up_event.channel == "telegram_bot"

    @pytest.mark.asyncio
    async def test_telegram_bot_should_autocreate_true_for_allowlisted(self, runner):
        """_should_autocreate_jorb returns True for telegram_bot with allowlisted sender."""
        event = IncomingEvent(
            channel="telegram_bot",
            sender="@alloweduser",
            sender_name="Allowed User",
            content="Hello",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        with patch(
            "services.telegram_allowlist.is_allowed_username",
            return_value=True,
        ):
            result = await runner._should_autocreate_jorb(event)
            assert result is True

    @pytest.mark.asyncio
    async def test_telegram_bot_should_autocreate_false_for_non_allowlisted(self, runner):
        """_should_autocreate_jorb returns False for telegram_bot with non-allowlisted sender."""
        event = IncomingEvent(
            channel="telegram_bot",
            sender="@randomuser",
            sender_name="Random User",
            content="Hello",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        with patch(
            "services.telegram_allowlist.is_allowed_username",
            return_value=False,
        ):
            result = await runner._should_autocreate_jorb(event)
            assert result is False

    @pytest.mark.asyncio
    async def test_telegram_channel_still_works(self, runner):
        """Existing telegram (Telethon) channel behavior unchanged."""
        event = IncomingEvent(
            channel="telegram",
            sender="@someuser",
            sender_name="Some User",
            content="Hello",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        with patch(
            "services.telegram_allowlist.is_allowed_username",
            return_value=True,
        ):
            result = await runner._should_autocreate_jorb(event)
            assert result is True

    @pytest.mark.asyncio
    async def test_sms_channel_still_works(self, runner):
        """Existing SMS channel behavior unchanged."""
        event = IncomingEvent(
            channel="sms",
            sender="+15551234567",
            sender_name="Mom",
            content="Hello",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        with patch.object(
            runner,
            "is_trusted_sender",
            new_callable=AsyncMock,
            return_value=True,
        ):
            result = await runner._should_autocreate_jorb(event)
            assert result is True
