"""
Integration tests for Android maintenance and health check scheduling in background loop.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from services.background_loop import BackgroundLoopService


class TestCronParsing:
    """Tests for cron string parsing."""

    def test_parses_standard_cron(self) -> None:
        """Parses standard 5-field cron format."""
        service = BackgroundLoopService()

        # Monthly: 0 3 1 * * (3 AM on 1st of month)
        minute, hour, day, month, dow = service._parse_simple_cron("0 3 1 * *")
        assert minute == 0
        assert hour == 3
        assert day == 1
        assert month is None
        assert dow is None

    def test_parses_weekly_cron(self) -> None:
        """Parses weekly cron format."""
        service = BackgroundLoopService()

        # Weekly: 0 4 * * 0 (4 AM on Sunday)
        minute, hour, day, month, dow = service._parse_simple_cron("0 4 * * 0")
        assert minute == 0
        assert hour == 4
        assert day is None
        assert month is None
        assert dow == 0

    def test_rejects_invalid_format(self) -> None:
        """Raises error for invalid cron format."""
        service = BackgroundLoopService()

        with pytest.raises(ValueError):
            service._parse_simple_cron("invalid")

        with pytest.raises(ValueError):
            service._parse_simple_cron("0 3 1 *")  # Only 4 fields


class TestMonthlyMaintenanceScheduling:
    """Tests for monthly maintenance scheduling."""

    @pytest.mark.asyncio
    async def test_runs_on_first_of_month(self) -> None:
        """Runs maintenance on first of month at configured time."""
        service = BackgroundLoopService()
        service._last_monthly_maintenance = None

        # Mock datetime to be 1st of month at 3:00 AM
        mock_now = datetime(2025, 2, 1, 3, 0, 0, tzinfo=timezone.utc)

        with patch.object(service, "_run_monthly_maintenance", new_callable=AsyncMock) as mock_run:
            await service._check_monthly_maintenance(mock_now, "0 3 1 * *")
            mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_if_already_run_this_month(self) -> None:
        """Skips if maintenance already ran this month."""
        service = BackgroundLoopService()
        service._last_monthly_maintenance = "2025-02"

        mock_now = datetime(2025, 2, 1, 3, 0, 0, tzinfo=timezone.utc)

        with patch.object(service, "_run_monthly_maintenance", new_callable=AsyncMock) as mock_run:
            await service._check_monthly_maintenance(mock_now, "0 3 1 * *")
            mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_wrong_day(self) -> None:
        """Skips if not the scheduled day."""
        service = BackgroundLoopService()
        service._last_monthly_maintenance = None

        # 15th of month
        mock_now = datetime(2025, 2, 15, 3, 0, 0, tzinfo=timezone.utc)

        with patch.object(service, "_run_monthly_maintenance", new_callable=AsyncMock) as mock_run:
            await service._check_monthly_maintenance(mock_now, "0 3 1 * *")
            mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_wrong_hour(self) -> None:
        """Skips if not the scheduled hour."""
        service = BackgroundLoopService()
        service._last_monthly_maintenance = None

        # Right day, wrong hour
        mock_now = datetime(2025, 2, 1, 10, 0, 0, tzinfo=timezone.utc)

        with patch.object(service, "_run_monthly_maintenance", new_callable=AsyncMock) as mock_run:
            await service._check_monthly_maintenance(mock_now, "0 3 1 * *")
            mock_run.assert_not_called()


class TestWeeklyHealthCheckScheduling:
    """Tests for weekly health check scheduling."""

    @pytest.mark.asyncio
    async def test_runs_on_sunday(self) -> None:
        """Runs health check on Sunday at configured time."""
        service = BackgroundLoopService()
        service._last_weekly_health_check = None

        # Sunday Feb 2, 2025 at 4:00 AM UTC
        # Note: 2025-02-02 is a Sunday
        mock_now = datetime(2025, 2, 2, 4, 0, 0, tzinfo=timezone.utc)

        with patch.object(service, "_run_weekly_health_check", new_callable=AsyncMock) as mock_run:
            await service._check_weekly_health_check(mock_now, "0 4 * * 0")
            mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_if_already_run_this_week(self) -> None:
        """Skips if health check already ran this week."""
        service = BackgroundLoopService()

        mock_now = datetime(2025, 2, 2, 4, 0, 0, tzinfo=timezone.utc)
        service._last_weekly_health_check = mock_now.strftime("%Y-W%W")

        with patch.object(service, "_run_weekly_health_check", new_callable=AsyncMock) as mock_run:
            await service._check_weekly_health_check(mock_now, "0 4 * * 0")
            mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_wrong_day_of_week(self) -> None:
        """Skips if not the scheduled day of week."""
        service = BackgroundLoopService()
        service._last_weekly_health_check = None

        # Monday (not Sunday)
        mock_now = datetime(2025, 2, 3, 4, 0, 0, tzinfo=timezone.utc)

        with patch.object(service, "_run_weekly_health_check", new_callable=AsyncMock) as mock_run:
            await service._check_weekly_health_check(mock_now, "0 4 * * 0")
            mock_run.assert_not_called()


class TestMonthlyMaintenanceExecution:
    """Tests for monthly maintenance execution."""

    @pytest.mark.asyncio
    async def test_sends_telegram_report_on_success(self) -> None:
        """Sends summary report via Telegram on success."""
        service = BackgroundLoopService()

        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.check_connection = AsyncMock(return_value=True)

        mock_telegram = MagicMock()
        mock_telegram.is_configured = True
        mock_telegram.send_notification = AsyncMock()

        mock_maintenance = MagicMock()
        mock_maintenance.check_security_patch = AsyncMock(return_value=MagicMock(
            success=True,
            details={"security_patch": "2025-01-05"},
        ))
        mock_maintenance.check_app_updates = AsyncMock(return_value=MagicMock(
            success=True,
        ))
        mock_maintenance.get_storage_info = AsyncMock(return_value=MagicMock(
            success=True,
            details={"used_percent": 60.0, "free_formatted": "40 GB"},
        ))
        mock_maintenance.clear_caches = AsyncMock(return_value=MagicMock(
            success=True,
            details={"action_taken": False},
        ))

        with (
            patch("services.android_client.get_android_client", return_value=mock_client),
            patch("services.android_maintenance.get_android_maintenance_service", return_value=mock_maintenance),
            patch("services.telegram_bot.TelegramBot", return_value=mock_telegram),
        ):
            await service._run_monthly_maintenance()

            mock_telegram.send_notification.assert_called_once()
            call_args = mock_telegram.send_notification.call_args
            message = call_args[0][0]
            assert "Monthly Android Maintenance Report" in message
            assert "2025-01-05" in message

    @pytest.mark.asyncio
    async def test_skips_when_device_not_connected(self) -> None:
        """Skips maintenance when device is not connected."""
        service = BackgroundLoopService()

        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.check_connection = AsyncMock(return_value=False)

        mock_telegram = MagicMock()
        mock_telegram.is_configured = True
        mock_telegram.send_notification = AsyncMock()

        with (
            patch("services.android_client.get_android_client", return_value=mock_client),
            patch("services.telegram_bot.TelegramBot", return_value=mock_telegram),
        ):
            await service._run_monthly_maintenance()

            mock_telegram.send_notification.assert_called_once()
            call_args = mock_telegram.send_notification.call_args
            message = call_args[0][0]
            assert "Skipped" in message


class TestWeeklyHealthCheckExecution:
    """Tests for weekly health check execution."""

    @pytest.mark.asyncio
    async def test_does_not_notify_when_healthy(self) -> None:
        """Does not send notification when no issues found."""
        service = BackgroundLoopService()

        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.check_connection = AsyncMock(return_value=True)
        mock_client.get_wifi_ssid = AsyncMock(return_value="MyNetwork")

        mock_telegram = MagicMock()
        mock_telegram.is_configured = True
        mock_telegram.send_notification = AsyncMock()

        mock_maintenance = MagicMock()
        mock_maintenance.get_battery_health = AsyncMock(return_value=MagicMock(
            success=True,
            details={"level_percent": "85", "health": "2"},
        ))
        mock_maintenance.test_app_launch = AsyncMock(return_value=MagicMock(
            success=True,
        ))

        with (
            patch("services.android_client.get_android_client", return_value=mock_client),
            patch("services.android_maintenance.get_android_maintenance_service", return_value=mock_maintenance),
            patch("services.telegram_bot.TelegramBot", return_value=mock_telegram),
        ):
            await service._run_weekly_health_check()

            # Should NOT send notification when healthy
            mock_telegram.send_notification.assert_not_called()

    @pytest.mark.asyncio
    async def test_notifies_when_issues_found(self) -> None:
        """Sends notification when issues are detected."""
        service = BackgroundLoopService()

        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.check_connection = AsyncMock(return_value=True)
        mock_client.get_wifi_ssid = AsyncMock(return_value=None)  # No WiFi

        mock_telegram = MagicMock()
        mock_telegram.is_configured = True
        mock_telegram.send_notification = AsyncMock()

        mock_maintenance = MagicMock()
        mock_maintenance.get_battery_health = AsyncMock(return_value=MagicMock(
            success=True,
            details={"level_percent": "15", "health": "2"},  # Low battery
        ))
        mock_maintenance.test_app_launch = AsyncMock(return_value=MagicMock(
            success=True,
        ))

        with (
            patch("services.android_client.get_android_client", return_value=mock_client),
            patch("services.android_maintenance.get_android_maintenance_service", return_value=mock_maintenance),
            patch("services.telegram_bot.TelegramBot", return_value=mock_telegram),
        ):
            await service._run_weekly_health_check()

            mock_telegram.send_notification.assert_called_once()
            call_args = mock_telegram.send_notification.call_args
            message = call_args[0][0]
            assert "Issues Detected" in message
            # Should mention both WiFi and battery issues
            assert "WiFi" in message or "Battery" in message


class TestBackgroundLoopStatus:
    """Tests for background loop status reporting."""

    def test_status_includes_maintenance_info(self) -> None:
        """Status includes maintenance-related fields."""
        service = BackgroundLoopService()
        service._last_monthly_maintenance = "2025-01"
        service._last_weekly_health_check = "2025-W05"

        status = service.get_status()

        assert "maintenance_task_running" in status
        assert "last_monthly_maintenance" in status
        assert "last_weekly_health_check" in status
        assert status["last_monthly_maintenance"] == "2025-01"
        assert status["last_weekly_health_check"] == "2025-W05"
