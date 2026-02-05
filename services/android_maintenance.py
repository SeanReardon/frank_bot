"""
Android device maintenance service.

Provides high-level maintenance operations for Android devices including
app updates, security patch checks, cache clearing, storage monitoring,
and device rebooting.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any

from services.android_client import AndroidClient, get_android_client
from services.stats import stats

logger = logging.getLogger(__name__)


@dataclass
class AppUpdateInfo:
    """Information about an app that can be updated."""

    package_name: str
    current_version: str | None = None
    available_version: str | None = None


@dataclass
class StorageInfo:
    """Device storage information."""

    total_bytes: int
    used_bytes: int
    free_bytes: int
    used_percent: float
    free_percent: float


@dataclass
class SecurityPatchInfo:
    """Security patch level information."""

    current_patch: str
    patch_date: str | None = None


@dataclass
class MaintenanceResult:
    """Result of a maintenance operation."""

    success: bool
    message: str
    details: dict[str, Any] | None = None
    error: str | None = None


class AndroidMaintenanceService:
    """
    Service for performing maintenance operations on Android devices.

    Uses ADB commands via AndroidClient to perform device upkeep tasks.
    """

    def __init__(self, client: AndroidClient | None = None):
        """
        Initialize the maintenance service.

        Args:
            client: AndroidClient instance. Uses singleton if not provided.
        """
        self._client = client or get_android_client()

    @property
    def is_configured(self) -> bool:
        """Check if the service is properly configured."""
        return self._client.is_configured

    async def check_app_updates(self) -> MaintenanceResult:
        """
        Check for pending app updates in the Play Store.

        Note: This requires interacting with the Play Store via UI automation,
        so it returns apps that have visible updates in My Apps section.

        Returns:
            MaintenanceResult with list of apps needing updates
        """
        maintenance_stats = stats.get_service_stats("android_maintenance")

        try:
            await self._client.connect()

            # Get list of user-installed packages
            result = await self._client.launch_app("com.android.vending")
            if not result.success:
                maintenance_stats.record_request(0, success=False, error="Play Store launch failed")
                return MaintenanceResult(
                    success=False,
                    message="Failed to launch Play Store",
                    error=result.error,
                )

            # Wait for Play Store to load
            await asyncio.sleep(2)

            # For now, we return a placeholder indicating manual check is needed
            # Full implementation would use LLM-in-the-loop to navigate to My Apps
            maintenance_stats.record_request(0, success=True)
            return MaintenanceResult(
                success=True,
                message="Play Store launched - check for updates manually or use LLM automation",
                details={
                    "action": "check_updates",
                    "requires_llm_automation": True,
                    "hint": "Navigate to My Apps -> Manage apps and device -> Updates available",
                },
            )

        except Exception as exc:
            error_msg = str(exc)
            maintenance_stats.record_request(0, success=False, error=error_msg)
            logger.exception("Failed to check app updates: %s", exc)
            return MaintenanceResult(
                success=False,
                message="Error checking app updates",
                error=error_msg,
            )

    async def install_app_updates(self) -> MaintenanceResult:
        """
        Install available app updates via Play Store.

        Note: This requires UI automation to navigate Play Store and
        trigger the Update All action.

        Returns:
            MaintenanceResult indicating update status
        """
        maintenance_stats = stats.get_service_stats("android_maintenance")

        try:
            await self._client.connect()

            # Launch Play Store
            result = await self._client.launch_app("com.android.vending")
            if not result.success:
                maintenance_stats.record_request(0, success=False, error="Play Store launch failed")
                return MaintenanceResult(
                    success=False,
                    message="Failed to launch Play Store",
                    error=result.error,
                )

            # Wait for Play Store to load
            await asyncio.sleep(2)

            maintenance_stats.record_request(0, success=True)
            return MaintenanceResult(
                success=True,
                message="Play Store launched - use LLM automation to complete updates",
                details={
                    "action": "install_updates",
                    "requires_llm_automation": True,
                    "workflow": [
                        "Tap profile icon (top right)",
                        "Tap 'Manage apps and device'",
                        "Tap 'Updates available'",
                        "Tap 'Update all'",
                        "Wait for updates to complete",
                    ],
                },
            )

        except Exception as exc:
            error_msg = str(exc)
            maintenance_stats.record_request(0, success=False, error=error_msg)
            logger.exception("Failed to install app updates: %s", exc)
            return MaintenanceResult(
                success=False,
                message="Error installing app updates",
                error=error_msg,
            )

    async def check_security_patch(self) -> MaintenanceResult:
        """
        Check the current security patch level.

        Reads the device's security patch date via ADB getprop.

        Returns:
            MaintenanceResult with security patch information
        """
        maintenance_stats = stats.get_service_stats("android_maintenance")

        try:
            await self._client.connect()

            # Get security patch level
            result = await self._client._run_adb(
                "shell", "getprop", "ro.build.version.security_patch"
            )

            if not result.success:
                maintenance_stats.record_request(result.elapsed_ms, success=False, error=result.error)
                return MaintenanceResult(
                    success=False,
                    message="Failed to read security patch level",
                    error=result.error,
                )

            current_patch = result.output.strip()

            # Get Android version for context
            version_result = await self._client._run_adb(
                "shell", "getprop", "ro.build.version.release"
            )
            android_version = version_result.output.strip() if version_result.success else "unknown"

            # Get build date
            build_date_result = await self._client._run_adb(
                "shell", "getprop", "ro.build.date"
            )
            build_date = build_date_result.output.strip() if build_date_result.success else None

            maintenance_stats.record_request(result.elapsed_ms, success=True)
            return MaintenanceResult(
                success=True,
                message=f"Security patch level: {current_patch}",
                details={
                    "security_patch": current_patch,
                    "android_version": android_version,
                    "build_date": build_date,
                    "note": "Compare with latest available patches for your device model",
                },
            )

        except Exception as exc:
            error_msg = str(exc)
            maintenance_stats.record_request(0, success=False, error=error_msg)
            logger.exception("Failed to check security patch: %s", exc)
            return MaintenanceResult(
                success=False,
                message="Error checking security patch",
                error=error_msg,
            )

    async def clear_caches(self, threshold_percent: float = 90.0) -> MaintenanceResult:
        """
        Clear app caches if storage is below threshold.

        Uses pm commands to clear cache for apps with largest caches.
        Only clears caches if storage used percentage exceeds threshold.

        Args:
            threshold_percent: Only clear caches if storage used > this percent

        Returns:
            MaintenanceResult with cache clearing status
        """
        maintenance_stats = stats.get_service_stats("android_maintenance")

        try:
            await self._client.connect()

            # First check storage
            storage_result = await self.get_storage_info()
            if not storage_result.success:
                return storage_result

            storage_info = storage_result.details
            used_percent = storage_info.get("used_percent", 0)

            if used_percent < threshold_percent:
                maintenance_stats.record_request(0, success=True)
                return MaintenanceResult(
                    success=True,
                    message=f"Storage at {used_percent:.1f}% - below {threshold_percent}% threshold, no cache clearing needed",
                    details={
                        "storage_used_percent": used_percent,
                        "threshold_percent": threshold_percent,
                        "action_taken": False,
                    },
                )

            # Get list of packages with cache sizes
            # This requires shell access with appropriate permissions
            result = await self._client._run_adb(
                "shell", "pm", "list", "packages", "-3"  # -3 = third-party apps
            )

            if not result.success:
                maintenance_stats.record_request(result.elapsed_ms, success=False, error=result.error)
                return MaintenanceResult(
                    success=False,
                    message="Failed to list packages for cache clearing",
                    error=result.error,
                )

            # Parse package names
            packages = []
            for line in result.output.splitlines():
                if line.startswith("package:"):
                    package = line.replace("package:", "").strip()
                    packages.append(package)

            # Clear cache for each package (requires appropriate permissions)
            cleared_count = 0
            errors = []

            for package in packages[:10]:  # Limit to first 10 to avoid long operations
                clear_result = await self._client._run_adb(
                    "shell", "pm", "clear-cache", package
                )
                if clear_result.success:
                    cleared_count += 1
                else:
                    # Cache clearing may require root or device owner permissions
                    errors.append(f"{package}: {clear_result.error}")

            maintenance_stats.record_request(0, success=True)

            if cleared_count > 0:
                return MaintenanceResult(
                    success=True,
                    message=f"Cleared cache for {cleared_count} apps",
                    details={
                        "apps_cleared": cleared_count,
                        "storage_before_percent": used_percent,
                        "errors": errors[:5] if errors else None,
                        "note": "Some caches may require device owner permissions to clear",
                    },
                )
            else:
                return MaintenanceResult(
                    success=True,
                    message="Cache clearing requires elevated permissions",
                    details={
                        "apps_attempted": len(packages[:10]),
                        "errors": errors[:5] if errors else None,
                        "suggestion": "Use Settings app via LLM automation to clear caches",
                    },
                )

        except Exception as exc:
            error_msg = str(exc)
            maintenance_stats.record_request(0, success=False, error=error_msg)
            logger.exception("Failed to clear caches: %s", exc)
            return MaintenanceResult(
                success=False,
                message="Error clearing caches",
                error=error_msg,
            )

    async def get_storage_info(self) -> MaintenanceResult:
        """
        Get internal storage usage information.

        Returns:
            MaintenanceResult with storage used/free percentages
        """
        maintenance_stats = stats.get_service_stats("android_maintenance")

        try:
            await self._client.connect()

            # Get storage info via df command
            result = await self._client._run_adb(
                "shell", "df", "/data"
            )

            if not result.success:
                maintenance_stats.record_request(result.elapsed_ms, success=False, error=result.error)
                return MaintenanceResult(
                    success=False,
                    message="Failed to get storage info",
                    error=result.error,
                )

            # Parse df output
            # Format: Filesystem  1K-blocks  Used  Available  Use%  Mounted on
            lines = result.output.strip().splitlines()
            if len(lines) < 2:
                maintenance_stats.record_request(result.elapsed_ms, success=False, error="Invalid df output")
                return MaintenanceResult(
                    success=False,
                    message="Could not parse storage info",
                    error="Invalid df output format",
                )

            # Parse the data line (second line)
            data_line = lines[1].split()
            if len(data_line) < 4:
                maintenance_stats.record_request(result.elapsed_ms, success=False, error="Invalid df data")
                return MaintenanceResult(
                    success=False,
                    message="Could not parse storage data",
                    error="Invalid df data format",
                )

            # Values are in 1K blocks
            try:
                total_kb = int(data_line[1])
                used_kb = int(data_line[2])
                available_kb = int(data_line[3])

                total_bytes = total_kb * 1024
                used_bytes = used_kb * 1024
                free_bytes = available_kb * 1024

                used_percent = (used_bytes / total_bytes) * 100 if total_bytes > 0 else 0
                free_percent = (free_bytes / total_bytes) * 100 if total_bytes > 0 else 0

            except (ValueError, IndexError) as exc:
                maintenance_stats.record_request(result.elapsed_ms, success=False, error=str(exc))
                return MaintenanceResult(
                    success=False,
                    message="Failed to parse storage values",
                    error=str(exc),
                )

            # Format for human readability
            def format_bytes(b: int) -> str:
                for unit in ["B", "KB", "MB", "GB", "TB"]:
                    if b < 1024:
                        return f"{b:.1f} {unit}"
                    b /= 1024
                return f"{b:.1f} PB"

            maintenance_stats.record_request(result.elapsed_ms, success=True)
            return MaintenanceResult(
                success=True,
                message=f"Storage: {used_percent:.1f}% used ({format_bytes(free_bytes)} free)",
                details={
                    "total_bytes": total_bytes,
                    "used_bytes": used_bytes,
                    "free_bytes": free_bytes,
                    "used_percent": round(used_percent, 1),
                    "free_percent": round(free_percent, 1),
                    "total_formatted": format_bytes(total_bytes),
                    "used_formatted": format_bytes(used_bytes),
                    "free_formatted": format_bytes(free_bytes),
                },
            )

        except Exception as exc:
            error_msg = str(exc)
            maintenance_stats.record_request(0, success=False, error=error_msg)
            logger.exception("Failed to get storage info: %s", exc)
            return MaintenanceResult(
                success=False,
                message="Error getting storage info",
                error=error_msg,
            )

    async def reboot_device(self, confirm: bool = False) -> MaintenanceResult:
        """
        Safely reboot the device.

        Requires explicit confirmation to prevent accidental reboots.

        Args:
            confirm: Must be True to actually perform the reboot

        Returns:
            MaintenanceResult indicating reboot status
        """
        maintenance_stats = stats.get_service_stats("android_maintenance")

        if not confirm:
            return MaintenanceResult(
                success=False,
                message="Reboot requires confirmation",
                error="Set confirm=true to actually reboot the device",
                details={
                    "action": "reboot",
                    "requires_confirmation": True,
                },
            )

        try:
            await self._client.connect()

            logger.warning("Initiating device reboot")

            # Send reboot command
            result = await self._client._run_adb("reboot")

            if not result.success:
                maintenance_stats.record_request(result.elapsed_ms, success=False, error=result.error)
                return MaintenanceResult(
                    success=False,
                    message="Failed to initiate reboot",
                    error=result.error,
                )

            maintenance_stats.record_request(result.elapsed_ms, success=True)
            return MaintenanceResult(
                success=True,
                message="Device reboot initiated",
                details={
                    "action": "reboot",
                    "note": "Device will be unavailable for 1-2 minutes",
                },
            )

        except Exception as exc:
            error_msg = str(exc)
            maintenance_stats.record_request(0, success=False, error=error_msg)
            logger.exception("Failed to reboot device: %s", exc)
            return MaintenanceResult(
                success=False,
                message="Error rebooting device",
                error=error_msg,
            )

    async def get_battery_health(self) -> MaintenanceResult:
        """
        Get detailed battery health information.

        Returns:
            MaintenanceResult with battery health details
        """
        maintenance_stats = stats.get_service_stats("android_maintenance")

        try:
            await self._client.connect()

            # Get battery info via dumpsys
            result = await self._client._run_adb("shell", "dumpsys", "battery")

            if not result.success:
                maintenance_stats.record_request(result.elapsed_ms, success=False, error=result.error)
                return MaintenanceResult(
                    success=False,
                    message="Failed to get battery info",
                    error=result.error,
                )

            # Parse battery info
            battery_info: dict[str, Any] = {}
            for line in result.output.splitlines():
                line = line.strip()
                if ":" in line:
                    key, value = line.split(":", 1)
                    key = key.strip().lower().replace(" ", "_")
                    value = value.strip()
                    battery_info[key] = value

            # Extract key metrics
            level = battery_info.get("level", "unknown")
            status = battery_info.get("status", "unknown")
            health = battery_info.get("health", "unknown")
            temperature = battery_info.get("temperature", "unknown")

            # Convert temperature (reported in tenths of degrees Celsius)
            temp_display = temperature
            try:
                temp_c = int(temperature) / 10
                temp_display = f"{temp_c:.1f}°C"
            except (ValueError, TypeError):
                pass

            maintenance_stats.record_request(result.elapsed_ms, success=True)
            return MaintenanceResult(
                success=True,
                message=f"Battery: {level}%, Health: {health}",
                details={
                    "level_percent": level,
                    "status": status,
                    "health": health,
                    "temperature": temp_display,
                    "plugged": battery_info.get("ac_powered") == "true"
                    or battery_info.get("usb_powered") == "true",
                    "raw_info": battery_info,
                },
            )

        except Exception as exc:
            error_msg = str(exc)
            maintenance_stats.record_request(0, success=False, error=error_msg)
            logger.exception("Failed to get battery health: %s", exc)
            return MaintenanceResult(
                success=False,
                message="Error getting battery health",
                error=error_msg,
            )

    async def test_app_launch(self, app_name: str = "settings") -> MaintenanceResult:
        """
        Test that an app can be launched successfully.

        Args:
            app_name: App name or package to test (default: settings)

        Returns:
            MaintenanceResult indicating if app launched successfully
        """
        maintenance_stats = stats.get_service_stats("android_maintenance")

        try:
            await self._client.connect()

            result = await self._client.launch_app(app_name)

            if not result.success:
                maintenance_stats.record_request(result.elapsed_ms, success=False, error=result.error)
                return MaintenanceResult(
                    success=False,
                    message=f"Failed to launch {app_name}",
                    error=result.error,
                )

            # Give app time to start
            await asyncio.sleep(1)

            # Verify by checking if something is on screen
            screen_result = await self._client.get_screen_xml()

            maintenance_stats.record_request(result.elapsed_ms, success=True)
            return MaintenanceResult(
                success=True,
                message=f"Successfully launched {app_name}",
                details={
                    "app": app_name,
                    "screen_populated": bool(screen_result.success and screen_result.output),
                },
            )

        except Exception as exc:
            error_msg = str(exc)
            maintenance_stats.record_request(0, success=False, error=error_msg)
            logger.exception("Failed to test app launch: %s", exc)
            return MaintenanceResult(
                success=False,
                message=f"Error testing app launch: {app_name}",
                error=error_msg,
            )


# Singleton instance
_maintenance_service: AndroidMaintenanceService | None = None


def get_android_maintenance_service() -> AndroidMaintenanceService:
    """Get the singleton AndroidMaintenanceService instance."""
    global _maintenance_service
    if _maintenance_service is None:
        _maintenance_service = AndroidMaintenanceService()
    return _maintenance_service


__all__ = [
    "AndroidMaintenanceService",
    "AppUpdateInfo",
    "StorageInfo",
    "SecurityPatchInfo",
    "MaintenanceResult",
    "get_android_maintenance_service",
]
