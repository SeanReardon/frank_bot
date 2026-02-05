"""
Integration tests for Android phone maintenance actions.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from actions.android_phone import (
    update_apps_action,
    check_security_action,
    reboot_action,
    get_storage_action,
    clear_cache_action,
    battery_health_action,
)
from services.android_maintenance import MaintenanceResult


class TestUpdateAppsAction:
    """Tests for update_apps_action."""

    @pytest.mark.asyncio
    async def test_returns_workflow_for_llm_automation(self) -> None:
        """Returns workflow when Play Store launches successfully."""
        mock_result = MaintenanceResult(
            success=True,
            message="Play Store launched",
            details={
                "requires_llm_automation": True,
                "workflow": ["Step 1", "Step 2"],
            },
        )

        with patch("services.android_maintenance.get_android_maintenance_service") as mock_get:
            mock_service = MagicMock()
            mock_service.check_app_updates = AsyncMock(return_value=mock_result)
            mock_service.install_app_updates = AsyncMock(return_value=mock_result)
            mock_get.return_value = mock_service

            result = await update_apps_action()

            assert result["success"] is True
            assert result["requires_llm_automation"] is True
            assert len(result["workflow"]) > 0

    @pytest.mark.asyncio
    async def test_handles_failure(self) -> None:
        """Returns error when check fails."""
        mock_result = MaintenanceResult(
            success=False,
            message="Failed to launch",
            error="App not installed",
        )

        with patch("services.android_maintenance.get_android_maintenance_service") as mock_get:
            mock_service = MagicMock()
            mock_service.check_app_updates = AsyncMock(return_value=mock_result)
            mock_get.return_value = mock_service

            result = await update_apps_action()

            assert result["success"] is False
            assert "error" in result


class TestCheckSecurityAction:
    """Tests for check_security_action."""

    @pytest.mark.asyncio
    async def test_returns_security_patch_info(self) -> None:
        """Returns security patch level."""
        mock_result = MaintenanceResult(
            success=True,
            message="Security patch level: 2025-01-05",
            details={
                "security_patch": "2025-01-05",
                "android_version": "15",
                "build_date": "2025-01-02",
            },
        )

        with patch("services.android_maintenance.get_android_maintenance_service") as mock_get:
            mock_service = MagicMock()
            mock_service.check_security_patch = AsyncMock(return_value=mock_result)
            mock_get.return_value = mock_service

            result = await check_security_action()

            assert result["success"] is True
            assert result["security_patch"] == "2025-01-05"
            assert result["android_version"] == "15"


class TestRebootAction:
    """Tests for reboot_action."""

    @pytest.mark.asyncio
    async def test_requires_confirmation(self) -> None:
        """Reboot requires confirm=true parameter."""
        mock_result = MaintenanceResult(
            success=False,
            message="Reboot requires confirmation",
            error="Set confirm=true to actually reboot",
        )

        with patch("services.android_maintenance.get_android_maintenance_service") as mock_get:
            mock_service = MagicMock()
            mock_service.reboot_device = AsyncMock(return_value=mock_result)
            mock_get.return_value = mock_service

            result = await reboot_action({"confirm": "false"})

            assert result["success"] is False
            mock_service.reboot_device.assert_called_once_with(confirm=False)

    @pytest.mark.asyncio
    async def test_reboots_when_confirmed(self) -> None:
        """Reboots when confirm=true."""
        mock_result = MaintenanceResult(
            success=True,
            message="Device reboot initiated",
            details={"action": "reboot"},
        )

        with patch("services.android_maintenance.get_android_maintenance_service") as mock_get:
            mock_service = MagicMock()
            mock_service.reboot_device = AsyncMock(return_value=mock_result)
            mock_get.return_value = mock_service

            result = await reboot_action({"confirm": "true"})

            assert result["success"] is True
            mock_service.reboot_device.assert_called_once_with(confirm=True)

    @pytest.mark.asyncio
    async def test_accepts_various_truthy_values(self) -> None:
        """Accepts yes, 1, true as confirmation."""
        mock_result = MaintenanceResult(
            success=True,
            message="Device reboot initiated",
        )

        with patch("services.android_maintenance.get_android_maintenance_service") as mock_get:
            mock_service = MagicMock()
            mock_service.reboot_device = AsyncMock(return_value=mock_result)
            mock_get.return_value = mock_service

            # Test "yes"
            await reboot_action({"confirm": "yes"})
            mock_service.reboot_device.assert_called_with(confirm=True)

            # Test "1"
            await reboot_action({"confirm": "1"})
            mock_service.reboot_device.assert_called_with(confirm=True)


class TestGetStorageAction:
    """Tests for get_storage_action."""

    @pytest.mark.asyncio
    async def test_returns_storage_info(self) -> None:
        """Returns storage usage details."""
        mock_result = MaintenanceResult(
            success=True,
            message="Storage: 60.0% used",
            details={
                "used_percent": 60.0,
                "free_percent": 40.0,
                "total_formatted": "100.0 GB",
                "used_formatted": "60.0 GB",
                "free_formatted": "40.0 GB",
            },
        )

        with patch("services.android_maintenance.get_android_maintenance_service") as mock_get:
            mock_service = MagicMock()
            mock_service.get_storage_info = AsyncMock(return_value=mock_result)
            mock_get.return_value = mock_service

            result = await get_storage_action()

            assert result["success"] is True
            assert result["used_percent"] == 60.0
            assert result["free_formatted"] == "40.0 GB"


class TestClearCacheAction:
    """Tests for clear_cache_action."""

    @pytest.mark.asyncio
    async def test_uses_default_threshold(self) -> None:
        """Uses 90% threshold by default."""
        mock_result = MaintenanceResult(
            success=True,
            message="Storage at 50% - below threshold",
            details={"action_taken": False, "storage_used_percent": 50.0},
        )

        with patch("services.android_maintenance.get_android_maintenance_service") as mock_get:
            mock_service = MagicMock()
            mock_service.clear_caches = AsyncMock(return_value=mock_result)
            mock_get.return_value = mock_service

            result = await clear_cache_action()

            mock_service.clear_caches.assert_called_once_with(threshold_percent=90.0)
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_accepts_custom_threshold(self) -> None:
        """Accepts custom threshold parameter."""
        mock_result = MaintenanceResult(
            success=True,
            message="Caches cleared",
            details={"action_taken": True},
        )

        with patch("services.android_maintenance.get_android_maintenance_service") as mock_get:
            mock_service = MagicMock()
            mock_service.clear_caches = AsyncMock(return_value=mock_result)
            mock_get.return_value = mock_service

            result = await clear_cache_action({"threshold": "80"})

            mock_service.clear_caches.assert_called_once_with(threshold_percent=80.0)


class TestBatteryHealthAction:
    """Tests for battery_health_action."""

    @pytest.mark.asyncio
    async def test_returns_battery_info(self) -> None:
        """Returns battery health details."""
        mock_result = MaintenanceResult(
            success=True,
            message="Battery: 85%, Health: 2",
            details={
                "level_percent": "85",
                "status": "2",
                "health": "2",
                "temperature": "27.5°C",
                "plugged": True,
                "raw_info": {"extra": "data"},
            },
        )

        with patch("services.android_maintenance.get_android_maintenance_service") as mock_get:
            mock_service = MagicMock()
            mock_service.get_battery_health = AsyncMock(return_value=mock_result)
            mock_get.return_value = mock_service

            result = await battery_health_action()

            assert result["success"] is True
            assert result["level_percent"] == "85"
            assert result["temperature"] == "27.5°C"
            assert result["plugged"] is True
            # raw_info should not be included in response
            assert "raw_info" not in result
