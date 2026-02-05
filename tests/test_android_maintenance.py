"""
Tests for AndroidMaintenanceService.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from services.android_maintenance import (
    AndroidMaintenanceService,
    MaintenanceResult,
    get_android_maintenance_service,
)
from services.android_client import ADBResult


class TestAndroidMaintenanceServiceInit:
    """Tests for AndroidMaintenanceService initialization."""

    def test_uses_provided_client(self) -> None:
        """Service uses provided client."""
        mock_client = MagicMock()
        mock_client.is_configured = True

        service = AndroidMaintenanceService(client=mock_client)

        assert service._client is mock_client
        assert service.is_configured is True

    def test_uses_default_client_when_none_provided(self) -> None:
        """Service uses singleton client when none provided."""
        with patch("services.android_maintenance.get_android_client") as mock_get:
            mock_client = MagicMock()
            mock_client.is_configured = True
            mock_get.return_value = mock_client

            service = AndroidMaintenanceService()

            mock_get.assert_called_once()
            assert service._client is mock_client


class TestCheckSecurityPatch:
    """Tests for check_security_patch method."""

    @pytest.mark.asyncio
    async def test_returns_security_patch_info(self) -> None:
        """Returns security patch level and related info."""
        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client._run_adb = AsyncMock(side_effect=[
            # Security patch
            ADBResult(success=True, output="2025-01-05\n", elapsed_ms=50),
            # Android version
            ADBResult(success=True, output="15\n", elapsed_ms=30),
            # Build date
            ADBResult(success=True, output="Thu Jan 2 10:00:00 UTC 2025\n", elapsed_ms=30),
        ])

        service = AndroidMaintenanceService(client=mock_client)
        result = await service.check_security_patch()

        assert result.success is True
        assert "2025-01-05" in result.message
        assert result.details["security_patch"] == "2025-01-05"
        assert result.details["android_version"] == "15"

    @pytest.mark.asyncio
    async def test_handles_adb_failure(self) -> None:
        """Returns error when ADB command fails."""
        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client._run_adb = AsyncMock(return_value=ADBResult(
            success=False,
            output="",
            error="Device offline",
            elapsed_ms=100,
        ))

        service = AndroidMaintenanceService(client=mock_client)
        result = await service.check_security_patch()

        assert result.success is False
        assert "Device offline" in result.error


class TestGetStorageInfo:
    """Tests for get_storage_info method."""

    @pytest.mark.asyncio
    async def test_parses_df_output_correctly(self) -> None:
        """Parses df command output and calculates percentages."""
        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        # Simulate df output: 100GB total, 60GB used, 40GB available
        df_output = """Filesystem     1K-blocks     Used Available Use% Mounted on
/dev/block/dm-0 104857600 62914560  41943040  60% /data"""
        mock_client._run_adb = AsyncMock(return_value=ADBResult(
            success=True,
            output=df_output,
            elapsed_ms=50,
        ))

        service = AndroidMaintenanceService(client=mock_client)
        result = await service.get_storage_info()

        assert result.success is True
        assert result.details["used_percent"] == 60.0
        assert result.details["free_percent"] == 40.0
        assert "60.0%" in result.message

    @pytest.mark.asyncio
    async def test_handles_invalid_df_output(self) -> None:
        """Returns error for invalid df output."""
        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client._run_adb = AsyncMock(return_value=ADBResult(
            success=True,
            output="invalid output",
            elapsed_ms=50,
        ))

        service = AndroidMaintenanceService(client=mock_client)
        result = await service.get_storage_info()

        assert result.success is False
        assert "parse" in result.message.lower()


class TestClearCaches:
    """Tests for clear_caches method."""

    @pytest.mark.asyncio
    async def test_skips_when_below_threshold(self) -> None:
        """Skips cache clearing when storage is below threshold."""
        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        # Storage at 50% used
        df_output = """Filesystem     1K-blocks     Used Available Use% Mounted on
/dev/block/dm-0 104857600 52428800  52428800  50% /data"""
        mock_client._run_adb = AsyncMock(return_value=ADBResult(
            success=True,
            output=df_output,
            elapsed_ms=50,
        ))

        service = AndroidMaintenanceService(client=mock_client)
        result = await service.clear_caches(threshold_percent=90.0)

        assert result.success is True
        assert "below" in result.message.lower()
        assert result.details["action_taken"] is False

    @pytest.mark.asyncio
    async def test_attempts_clearing_when_above_threshold(self) -> None:
        """Attempts cache clearing when storage exceeds threshold."""
        mock_client = MagicMock()
        mock_client.connect = AsyncMock()

        # First call: storage at 95% used
        df_output = """Filesystem     1K-blocks     Used Available Use% Mounted on
/dev/block/dm-0 104857600 99614720   5242880  95% /data"""

        mock_client._run_adb = AsyncMock(side_effect=[
            # df command
            ADBResult(success=True, output=df_output, elapsed_ms=50),
            # pm list packages
            ADBResult(success=True, output="package:com.test.app1\npackage:com.test.app2\n", elapsed_ms=50),
            # pm clear-cache calls (will fail without root)
            ADBResult(success=False, output="", error="Permission denied", elapsed_ms=50),
            ADBResult(success=False, output="", error="Permission denied", elapsed_ms=50),
        ])

        service = AndroidMaintenanceService(client=mock_client)
        result = await service.clear_caches(threshold_percent=90.0)

        assert result.success is True
        # Should indicate elevated permissions needed
        assert "permission" in result.message.lower() or result.details.get("errors")


class TestRebootDevice:
    """Tests for reboot_device method."""

    @pytest.mark.asyncio
    async def test_requires_confirmation(self) -> None:
        """Reboot requires explicit confirmation."""
        mock_client = MagicMock()

        service = AndroidMaintenanceService(client=mock_client)
        result = await service.reboot_device(confirm=False)

        assert result.success is False
        assert "confirmation" in result.message.lower()
        # Should not have attempted connect
        mock_client.connect.assert_not_called()

    @pytest.mark.asyncio
    async def test_reboots_when_confirmed(self) -> None:
        """Reboots device when confirmation is True."""
        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client._run_adb = AsyncMock(return_value=ADBResult(
            success=True,
            output="",
            elapsed_ms=100,
        ))

        service = AndroidMaintenanceService(client=mock_client)
        result = await service.reboot_device(confirm=True)

        assert result.success is True
        assert "initiated" in result.message.lower()
        mock_client._run_adb.assert_called_once_with("reboot")

    @pytest.mark.asyncio
    async def test_handles_reboot_failure(self) -> None:
        """Returns error when reboot command fails."""
        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client._run_adb = AsyncMock(return_value=ADBResult(
            success=False,
            output="",
            error="ADB connection lost",
            elapsed_ms=100,
        ))

        service = AndroidMaintenanceService(client=mock_client)
        result = await service.reboot_device(confirm=True)

        assert result.success is False
        assert "ADB connection lost" in result.error


class TestCheckAppUpdates:
    """Tests for check_app_updates method."""

    @pytest.mark.asyncio
    async def test_launches_play_store(self) -> None:
        """Launches Play Store for manual/LLM update check."""
        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.launch_app = AsyncMock(return_value=ADBResult(
            success=True,
            output="Launching...",
            elapsed_ms=500,
        ))

        service = AndroidMaintenanceService(client=mock_client)
        result = await service.check_app_updates()

        assert result.success is True
        assert result.details["requires_llm_automation"] is True
        mock_client.launch_app.assert_called_once_with("com.android.vending")

    @pytest.mark.asyncio
    async def test_handles_play_store_launch_failure(self) -> None:
        """Returns error when Play Store fails to launch."""
        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.launch_app = AsyncMock(return_value=ADBResult(
            success=False,
            output="",
            error="App not installed",
            elapsed_ms=100,
        ))

        service = AndroidMaintenanceService(client=mock_client)
        result = await service.check_app_updates()

        assert result.success is False
        assert "Play Store" in result.message


class TestInstallAppUpdates:
    """Tests for install_app_updates method."""

    @pytest.mark.asyncio
    async def test_provides_workflow_instructions(self) -> None:
        """Returns workflow for LLM automation."""
        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.launch_app = AsyncMock(return_value=ADBResult(
            success=True,
            output="Launching...",
            elapsed_ms=500,
        ))

        service = AndroidMaintenanceService(client=mock_client)
        result = await service.install_app_updates()

        assert result.success is True
        assert result.details["requires_llm_automation"] is True
        assert "workflow" in result.details
        assert len(result.details["workflow"]) > 0


class TestGetBatteryHealth:
    """Tests for get_battery_health method."""

    @pytest.mark.asyncio
    async def test_parses_battery_info(self) -> None:
        """Parses dumpsys battery output correctly."""
        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        battery_output = """Current Battery Service state:
  AC powered: false
  USB powered: true
  Wireless powered: false
  Max charging current: 500000
  Max charging voltage: 5000000
  Charge counter: 1234567
  status: 2
  health: 2
  present: true
  level: 85
  scale: 100
  temperature: 275
  technology: Li-ion"""
        mock_client._run_adb = AsyncMock(return_value=ADBResult(
            success=True,
            output=battery_output,
            elapsed_ms=50,
        ))

        service = AndroidMaintenanceService(client=mock_client)
        result = await service.get_battery_health()

        assert result.success is True
        assert "85" in result.details["level_percent"]
        assert "27.5°C" in result.details["temperature"]
        assert result.details["plugged"] is True

    @pytest.mark.asyncio
    async def test_handles_missing_battery_info(self) -> None:
        """Handles ADB failure gracefully."""
        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client._run_adb = AsyncMock(return_value=ADBResult(
            success=False,
            output="",
            error="Device offline",
            elapsed_ms=100,
        ))

        service = AndroidMaintenanceService(client=mock_client)
        result = await service.get_battery_health()

        assert result.success is False


class TestTestAppLaunch:
    """Tests for test_app_launch method."""

    @pytest.mark.asyncio
    async def test_launches_and_verifies_app(self) -> None:
        """Launches app and verifies screen content."""
        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.launch_app = AsyncMock(return_value=ADBResult(
            success=True,
            output="Launching...",
            elapsed_ms=500,
        ))
        mock_client.get_screen_xml = AsyncMock(return_value=ADBResult(
            success=True,
            output="<hierarchy><node/></hierarchy>",
            elapsed_ms=200,
        ))

        service = AndroidMaintenanceService(client=mock_client)
        result = await service.test_app_launch("settings")

        assert result.success is True
        assert result.details["screen_populated"] is True
        mock_client.launch_app.assert_called_once_with("settings")

    @pytest.mark.asyncio
    async def test_reports_launch_failure(self) -> None:
        """Reports failure when app doesn't launch."""
        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.launch_app = AsyncMock(return_value=ADBResult(
            success=False,
            output="",
            error="App not found",
            elapsed_ms=100,
        ))

        service = AndroidMaintenanceService(client=mock_client)
        result = await service.test_app_launch("nonexistent_app")

        assert result.success is False
        assert "nonexistent_app" in result.message


class TestSingleton:
    """Tests for singleton accessor."""

    def test_returns_same_instance(self) -> None:
        """get_android_maintenance_service returns same instance."""
        with patch("services.android_maintenance.get_android_client"):
            # Reset singleton
            import services.android_maintenance as module
            module._maintenance_service = None

            service1 = get_android_maintenance_service()
            service2 = get_android_maintenance_service()

            assert service1 is service2


class TestMaintenanceResult:
    """Tests for MaintenanceResult dataclass."""

    def test_minimal_result(self) -> None:
        """Creates result with minimal fields."""
        result = MaintenanceResult(success=True, message="Done")

        assert result.success is True
        assert result.message == "Done"
        assert result.details is None
        assert result.error is None

    def test_full_result(self) -> None:
        """Creates result with all fields."""
        result = MaintenanceResult(
            success=False,
            message="Failed",
            details={"foo": "bar"},
            error="Something went wrong",
        )

        assert result.success is False
        assert result.details["foo"] == "bar"
        assert result.error == "Something went wrong"
