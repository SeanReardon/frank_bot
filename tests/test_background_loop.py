"""
Tests for the Background Event Loop service.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.background_loop import (
    BackgroundLoopService,
    start_background_loop,
    stop_background_loop,
    get_background_loop_status,
)


@pytest.fixture
def mock_storage():
    """Create a mock JorbStorage."""
    storage = MagicMock()
    storage.get_open_jorbs_with_messages = AsyncMock(return_value=[])
    storage.list_jorbs = AsyncMock(return_value=[])
    storage.get_messages = AsyncMock(return_value=[])
    return storage


@pytest.fixture
def mock_email_service():
    """Create a mock EmailService."""
    service = MagicMock()
    service.is_configured = False
    service.send_daily_digest = AsyncMock(return_value=True)
    return service


@pytest.fixture
def mock_context_reset_service():
    """Create a mock ContextResetService."""
    service = MagicMock()
    service.is_configured = False
    service.maybe_reset_context = MagicMock(return_value=False)
    service.get_reset_status = MagicMock(return_value={"last_reset_at": None})
    return service


@pytest.fixture
def background_service(mock_storage, mock_email_service, mock_context_reset_service):
    """Create a BackgroundLoopService with mocked dependencies."""
    return BackgroundLoopService(
        storage=mock_storage,
        email_service=mock_email_service,
        context_reset_service=mock_context_reset_service,
    )


class TestBackgroundLoopService:
    """Tests for BackgroundLoopService class."""

    def test_initial_state(self, background_service):
        """Test service initializes in stopped state."""
        assert not background_service.is_running
        status = background_service.get_status()
        assert not status["running"]
        assert not status["heartbeat_task_running"]
        assert not status["digest_task_running"]

    @pytest.mark.asyncio
    async def test_start_sets_running(self, background_service):
        """Test start() sets running flag and creates tasks."""
        with patch(
            "services.background_loop.initialize_telegram_jorb_router",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "services.background_loop.initialize_telegram_bot_router",
            new_callable=AsyncMock,
            return_value=False,
        ):
            await background_service.start()

            assert background_service.is_running
            status = background_service.get_status()
            assert status["running"]
            assert status["heartbeat_task_running"]
            assert status["digest_task_running"]

            # Clean up
            await background_service.stop()

    @pytest.mark.asyncio
    async def test_stop_cleans_up(self, background_service):
        """Test stop() cleans up tasks and sets state."""
        with patch(
            "services.background_loop.initialize_telegram_jorb_router",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "services.background_loop.initialize_telegram_bot_router",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "services.background_loop.shutdown_telegram_jorb_router",
            new_callable=AsyncMock,
        ), patch(
            "services.background_loop.shutdown_telegram_bot_router",
            new_callable=AsyncMock,
        ):
            await background_service.start()
            await background_service.stop()

            assert not background_service.is_running
            status = background_service.get_status()
            assert not status["running"]

    @pytest.mark.asyncio
    async def test_double_start_warns(self, background_service, caplog):
        """Test starting twice logs a warning."""
        with patch(
            "services.background_loop.initialize_telegram_jorb_router",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "services.background_loop.initialize_telegram_bot_router",
            new_callable=AsyncMock,
            return_value=False,
        ):
            await background_service.start()
            await background_service.start()

            assert "already running" in caplog.text

            await background_service.stop()

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self, background_service):
        """Test stop() when service is not running does nothing."""
        # Should not raise
        await background_service.stop()
        assert not background_service.is_running


class TestHeartbeatLoop:
    """Tests for heartbeat functionality."""

    @pytest.mark.asyncio
    async def test_run_heartbeat_checks_stale_jorbs(
        self, background_service, mock_storage
    ):
        """Test heartbeat runs stale jorb check."""
        mock_agent_runner = MagicMock()
        mock_agent_runner.check_stale_jorbs = AsyncMock(return_value=[])
        mock_agent_runner.check_expired_jorbs = AsyncMock(return_value=[])

        with patch(
            "services.background_loop.AgentRunner",
            return_value=mock_agent_runner,
        ):
            await background_service._run_heartbeat()

            mock_agent_runner.check_stale_jorbs.assert_called_once()
            mock_agent_runner.check_expired_jorbs.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_heartbeat_checks_context_reset(
        self,
        mock_storage,
        mock_email_service,
    ):
        """Test heartbeat checks context reset when configured."""
        mock_context_reset = MagicMock()
        mock_context_reset.is_configured = True
        mock_context_reset.maybe_reset_context = MagicMock(return_value=True)
        mock_context_reset.perform_context_reset = AsyncMock(
            return_value=MagicMock(jorb_handoffs=[])
        )
        mock_context_reset.get_reset_status = MagicMock(return_value={})

        service = BackgroundLoopService(
            storage=mock_storage,
            email_service=mock_email_service,
            context_reset_service=mock_context_reset,
        )

        with patch(
            "services.background_loop.AgentRunner",
            return_value=MagicMock(
                check_stale_jorbs=AsyncMock(return_value=[]),
                check_expired_jorbs=AsyncMock(return_value=[]),
            ),
        ):
            await service._run_heartbeat()

            mock_context_reset.maybe_reset_context.assert_called_once()
            mock_context_reset.perform_context_reset.assert_called_once()

    @pytest.mark.asyncio
    async def test_heartbeat_logs_stale_jorbs(
        self, background_service, caplog
    ):
        """Test heartbeat logs when jorbs are paused."""
        import logging
        caplog.set_level(logging.INFO)

        mock_agent_runner = MagicMock()
        mock_agent_runner.check_stale_jorbs = AsyncMock(
            return_value=["jorb_123", "jorb_456"]
        )
        mock_agent_runner.check_expired_jorbs = AsyncMock(return_value=[])

        with patch(
            "services.background_loop.AgentRunner",
            return_value=mock_agent_runner,
        ):
            await background_service._check_stale_jorbs()

            assert "Auto-paused 2 stale jorb(s)" in caplog.text


class TestDigestLoop:
    """Tests for daily digest functionality."""

    @pytest.mark.asyncio
    async def test_send_digest_when_configured(
        self, mock_storage, mock_context_reset_service
    ):
        """Test digest sends when email is configured."""
        mock_email = MagicMock()
        mock_email.is_configured = True
        mock_email.send_daily_digest = AsyncMock(return_value=True)

        service = BackgroundLoopService(
            storage=mock_storage,
            email_service=mock_email,
            context_reset_service=mock_context_reset_service,
        )

        await service._send_daily_digest()

        mock_email.send_daily_digest.assert_called_once()

    @pytest.mark.asyncio
    async def test_digest_skipped_when_not_configured(
        self, background_service, mock_email_service
    ):
        """Test digest is skipped when email not configured."""
        mock_email_service.is_configured = False

        await background_service._send_daily_digest()

        mock_email_service.send_daily_digest.assert_not_called()

    @pytest.mark.asyncio
    async def test_digest_not_sent_twice_same_day(
        self, mock_storage, mock_context_reset_service
    ):
        """Test digest is only sent once per day."""
        mock_email = MagicMock()
        mock_email.is_configured = True
        mock_email.send_daily_digest = AsyncMock(return_value=True)

        service = BackgroundLoopService(
            storage=mock_storage,
            email_service=mock_email,
            context_reset_service=mock_context_reset_service,
        )

        # Mark as already sent today
        service._last_digest_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # This should not send because we already "sent" today
        await service._check_digest_time()

        mock_email.send_daily_digest.assert_not_called()


class TestModuleLevelFunctions:
    """Tests for module-level convenience functions."""

    @pytest.mark.asyncio
    async def test_start_and_stop_background_loop(self):
        """Test module-level start and stop functions."""
        with patch(
            "services.background_loop.initialize_telegram_jorb_router",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "services.background_loop.initialize_telegram_bot_router",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "services.background_loop.shutdown_telegram_jorb_router",
            new_callable=AsyncMock,
        ), patch(
            "services.background_loop.shutdown_telegram_bot_router",
            new_callable=AsyncMock,
        ):
            # Start the loop
            await start_background_loop()

            status = get_background_loop_status()
            assert status["running"]

            # Stop the loop
            await stop_background_loop()

            status = get_background_loop_status()
            assert not status["running"]

    def test_get_status_when_not_initialized(self):
        """Test get_background_loop_status when not initialized."""
        import services.background_loop as module

        # Ensure module-level service is None
        original = module._background_service
        module._background_service = None

        try:
            status = get_background_loop_status()
            assert not status["running"]
            assert "not initialized" in status.get("message", "")
        finally:
            module._background_service = original


class TestErrorHandling:
    """Tests for error handling in background loops."""

    @pytest.mark.asyncio
    async def test_heartbeat_continues_after_error(
        self, background_service, caplog
    ):
        """Test heartbeat loop continues after an error."""
        error_count = 0

        async def failing_check():
            nonlocal error_count
            error_count += 1
            raise Exception("Test error")

        with patch.object(
            background_service,
            "_check_stale_jorbs",
            side_effect=failing_check,
        ), patch.object(
            background_service,
            "_check_context_reset",
            new_callable=AsyncMock,
        ):
            # Run heartbeat directly - should not raise
            await background_service._run_heartbeat()

            assert "Error during heartbeat" in caplog.text

    @pytest.mark.asyncio
    async def test_digest_continues_after_error(
        self, background_service, caplog
    ):
        """Test digest loop handles errors gracefully."""
        mock_email = MagicMock()
        mock_email.is_configured = True
        mock_email.send_daily_digest = AsyncMock(side_effect=Exception("SMTP error"))

        background_service._email_service = mock_email

        # Should not raise
        await background_service._send_daily_digest()

        assert "Error sending daily digest" in caplog.text


class TestTelegramRouterIntegration:
    """Tests for Telegram router integration."""

    @pytest.mark.asyncio
    async def test_telegram_router_initialized_on_start(self, background_service):
        """Test Telegram router is initialized when starting."""
        mock_init = AsyncMock(return_value=True)

        with patch(
            "services.background_loop.initialize_telegram_jorb_router",
            mock_init,
        ), patch(
            "services.background_loop.initialize_telegram_bot_router",
            new_callable=AsyncMock,
            return_value=False,
        ):
            await background_service.start()

            mock_init.assert_called_once()

            await background_service.stop()

    @pytest.mark.asyncio
    async def test_telegram_router_shutdown_on_stop(self, background_service):
        """Test Telegram router is shut down when stopping."""
        mock_shutdown = AsyncMock()

        with patch(
            "services.background_loop.initialize_telegram_jorb_router",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "services.background_loop.initialize_telegram_bot_router",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "services.background_loop.shutdown_telegram_jorb_router",
            mock_shutdown,
        ), patch(
            "services.background_loop.shutdown_telegram_bot_router",
            new_callable=AsyncMock,
        ):
            await background_service.start()
            await background_service.stop()

            mock_shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_status_includes_telegram_router_status(self, background_service):
        """Test status includes Telegram router information."""
        mock_router_status = {
            "initialized": True,
            "telegram_configured": True,
            "agent_configured": True,
            "pending_messages": 0,
        }

        with patch(
            "services.background_loop.get_router_status",
            return_value=mock_router_status,
        ):
            status = background_service.get_status()

            assert "telegram_router" in status
            assert status["telegram_router"] == mock_router_status


class TestGracefulShutdown:
    """Tests for graceful shutdown handling."""

    @pytest.mark.asyncio
    async def test_tasks_cancelled_on_stop(self, background_service):
        """Test background tasks are properly cancelled on stop."""
        with patch(
            "services.background_loop.initialize_telegram_jorb_router",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "services.background_loop.initialize_telegram_bot_router",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "services.background_loop.shutdown_telegram_jorb_router",
            new_callable=AsyncMock,
        ), patch(
            "services.background_loop.shutdown_telegram_bot_router",
            new_callable=AsyncMock,
        ):
            await background_service.start()

            # Verify tasks are running
            assert background_service._heartbeat_task is not None
            assert not background_service._heartbeat_task.done()

            await background_service.stop()

            # Tasks should be done (cancelled)
            assert background_service._heartbeat_task.done()
            assert background_service._digest_task.done()

    @pytest.mark.asyncio
    async def test_shutdown_event_stops_loops(self, background_service):
        """Test shutdown event properly signals loops to stop."""
        with patch(
            "services.background_loop.initialize_telegram_jorb_router",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "services.background_loop.initialize_telegram_bot_router",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "services.background_loop.shutdown_telegram_jorb_router",
            new_callable=AsyncMock,
        ), patch(
            "services.background_loop.shutdown_telegram_bot_router",
            new_callable=AsyncMock,
        ):
            await background_service.start()

            # Shutdown event should not be set initially
            assert not background_service._shutdown_event.is_set()

            await background_service.stop()

            # Shutdown event should be set
            assert background_service._shutdown_event.is_set()
