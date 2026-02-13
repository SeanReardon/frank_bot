"""
Tests for AgentRunner._send_message() channel routing.

Verifies that channel='telegram_bot' routes through TelegramBot.send_notification()
and that existing channels (telegram, sms) continue working unchanged.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.agent_runner import AgentRunner


@pytest.fixture
def runner():
    """Create an AgentRunner with mocked storage and API key."""
    with patch("services.agent_runner.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            openai_api_key="test-key",
            agent_spend_limit=100.0,
        )
        return AgentRunner(
            storage=MagicMock(),
            openai_api_key="test-key",
        )


class TestSendMessageChannelRouting:
    """Tests for _send_message channel routing."""

    @pytest.mark.asyncio
    async def test_telegram_bot_routes_through_bot_api(self, runner):
        """channel='telegram_bot' routes through _send_telegram_bot_message."""
        with patch.object(
            runner,
            "_send_telegram_bot_message",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_bot:
            result = await runner._send_message("telegram_bot", "12345", "Hello!")

            assert result is True
            mock_bot.assert_called_once_with(chat_id="12345", text="Hello!")

    @pytest.mark.asyncio
    async def test_telegram_routes_through_telethon(self, runner):
        """channel='telegram' still routes through TelegramClientService."""
        mock_service = MagicMock()
        mock_service.send_message = AsyncMock(
            return_value=MagicMock(success=True)
        )

        with patch(
            "services.telegram_client.TelegramClientService",
            return_value=mock_service,
        ):
            result = await runner._send_message("telegram", "@alice", "Hello!")

            assert result is True
            mock_service.send_message.assert_called_once_with("@alice", "Hello!")

    @pytest.mark.asyncio
    async def test_sms_routes_through_telnyx(self, runner):
        """channel='sms' still routes through TelnyxSMSService."""
        mock_service = MagicMock()
        mock_service.send_sms = MagicMock(return_value=MagicMock(success=True))

        with patch(
            "services.telnyx_sms.TelnyxSMSService",
            return_value=mock_service,
        ):
            result = await runner._send_message("sms", "+15551234567", "Hello!")

            assert result is True
            mock_service.send_sms.assert_called_once_with("+15551234567", "Hello!")

    @pytest.mark.asyncio
    async def test_telegram_bot_failure_returns_false(self, runner):
        """channel='telegram_bot' returns False on failure."""
        with patch.object(
            runner,
            "_send_telegram_bot_message",
            new_callable=AsyncMock,
            return_value=False,
        ):
            result = await runner._send_message("telegram_bot", "12345", "Hello!")

            assert result is False

    @pytest.mark.asyncio
    async def test_unknown_channel_returns_false(self, runner):
        """Unknown channel returns False."""
        result = await runner._send_message("carrier_pigeon", "@alice", "Hello!")
        assert result is False
