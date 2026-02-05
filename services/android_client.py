"""
Android device control service via ADB over network.

Provides low-level ADB commands for controlling an Android device
connected via ADB TCP/IP (wireless debugging).
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from dataclasses import dataclass

from services.stats import stats

logger = logging.getLogger(__name__)

# Default ADB connection settings
DEFAULT_ADB_HOST = "10.0.0.95"
DEFAULT_ADB_PORT = 5555
DEFAULT_ADB_TIMEOUT = 30  # seconds


@dataclass
class ADBResult:
    """Result of an ADB command execution."""

    success: bool
    output: str
    error: str | None = None
    elapsed_ms: float = 0


@dataclass
class UIElement:
    """Represents a UI element from the accessibility tree."""

    text: str
    content_desc: str
    resource_id: str
    class_name: str
    package: str
    bounds: tuple[int, int, int, int]  # left, top, right, bottom
    clickable: bool
    scrollable: bool
    focused: bool
    enabled: bool

    @property
    def center(self) -> tuple[int, int]:
        """Calculate center coordinates for tapping."""
        left, top, right, bottom = self.bounds
        return ((left + right) // 2, (top + bottom) // 2)


class AndroidClient:
    """
    Client for controlling an Android device via ADB over TCP/IP.
    
    Uses the standard ADB command-line tool to communicate with the device.
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        timeout: int = DEFAULT_ADB_TIMEOUT,
    ):
        self._host = host or os.getenv("ANDROID_ADB_HOST", DEFAULT_ADB_HOST)
        self._port = port or int(os.getenv("ANDROID_ADB_PORT", str(DEFAULT_ADB_PORT)))
        self._timeout = timeout
        self._device_serial = f"{self._host}:{self._port}"
        self._connected = False

    @property
    def device_serial(self) -> str:
        """Return the device serial (host:port)."""
        return self._device_serial

    @property
    def is_configured(self) -> bool:
        """Check if the service has required configuration."""
        return bool(self._host and self._port)

    async def _run_adb(self, *args: str, timeout: int | None = None) -> ADBResult:
        """
        Run an ADB command and return the result.
        
        Args:
            *args: ADB command arguments (without 'adb' prefix)
            timeout: Optional timeout override
            
        Returns:
            ADBResult with success status and output
        """
        cmd_timeout = timeout or self._timeout
        cmd = ["adb", "-s", self._device_serial, *args]
        
        adb_stats = stats.get_service_stats("android_adb")
        start = time.time()
        
        try:
            logger.debug("Running ADB command: %s", " ".join(cmd))
            
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=cmd_timeout,
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                elapsed_ms = (time.time() - start) * 1000
                adb_stats.record_request(elapsed_ms, success=False, error="Timeout")
                return ADBResult(
                    success=False,
                    output="",
                    error=f"ADB command timed out after {cmd_timeout}s",
                    elapsed_ms=elapsed_ms,
                )
            
            elapsed_ms = (time.time() - start) * 1000
            output = stdout.decode("utf-8", errors="replace")
            error_output = stderr.decode("utf-8", errors="replace")
            
            if proc.returncode == 0:
                adb_stats.record_request(elapsed_ms, success=True)
                return ADBResult(
                    success=True,
                    output=output,
                    elapsed_ms=elapsed_ms,
                )
            else:
                adb_stats.record_request(elapsed_ms, success=False, error=error_output)
                return ADBResult(
                    success=False,
                    output=output,
                    error=error_output or f"ADB command failed with code {proc.returncode}",
                    elapsed_ms=elapsed_ms,
                )
                
        except Exception as exc:
            elapsed_ms = (time.time() - start) * 1000
            error_msg = str(exc)
            adb_stats.record_request(elapsed_ms, success=False, error=error_msg)
            logger.exception("ADB command failed: %s", " ".join(cmd))
            return ADBResult(
                success=False,
                output="",
                error=error_msg,
                elapsed_ms=elapsed_ms,
            )

    async def connect(self) -> ADBResult:
        """
        Connect to the Android device via ADB TCP/IP.
        
        Returns:
            ADBResult indicating connection success
        """
        result = await self._run_adb("connect", self._device_serial)
        if result.success or "already connected" in result.output.lower():
            self._connected = True
            result.success = True
        return result

    async def disconnect(self) -> ADBResult:
        """Disconnect from the Android device."""
        result = await self._run_adb("disconnect", self._device_serial)
        self._connected = False
        return result

    async def check_connection(self) -> bool:
        """Check if the device is connected and responding."""
        result = await self._run_adb("shell", "echo", "ping")
        return result.success and "ping" in result.output

    async def get_device_info(self) -> dict[str, str]:
        """Get basic device information."""
        info = {}
        
        # Get device model
        result = await self._run_adb("shell", "getprop", "ro.product.model")
        if result.success:
            info["model"] = result.output.strip()
        
        # Get Android version
        result = await self._run_adb("shell", "getprop", "ro.build.version.release")
        if result.success:
            info["android_version"] = result.output.strip()
        
        # Get build number
        result = await self._run_adb("shell", "getprop", "ro.build.display.id")
        if result.success:
            info["build"] = result.output.strip()
        
        return info

    async def get_screen_xml(self) -> ADBResult:
        """
        Dump the UI accessibility tree as XML.
        
        This is the primary way to understand what's on screen.
        
        Returns:
            ADBResult with XML content in output field
        """
        # Dump UI hierarchy to device
        dump_result = await self._run_adb(
            "shell", "uiautomator", "dump", "/sdcard/ui_dump.xml"
        )
        if not dump_result.success:
            return dump_result
        
        # Read the XML content
        result = await self._run_adb("shell", "cat", "/sdcard/ui_dump.xml")
        
        # Clean up
        await self._run_adb("shell", "rm", "-f", "/sdcard/ui_dump.xml")
        
        return result

    async def take_screenshot(self, local_path: str | None = None) -> ADBResult:
        """
        Take a screenshot of the device screen.
        
        Args:
            local_path: Optional local path to save the screenshot
            
        Returns:
            ADBResult with local file path in output field
        """
        device_path = "/sdcard/screenshot.png"
        
        # Take screenshot on device
        result = await self._run_adb("shell", "screencap", "-p", device_path)
        if not result.success:
            return result
        
        # Pull to local if path specified, otherwise use temp
        if not local_path:
            local_path = f"/tmp/android_screenshot_{int(time.time())}.png"
        
        result = await self._run_adb("pull", device_path, local_path)
        if result.success:
            result.output = local_path
        
        # Clean up device file
        await self._run_adb("shell", "rm", "-f", device_path)
        
        return result

    async def tap(self, x: int, y: int) -> ADBResult:
        """
        Tap at the specified coordinates.
        
        Args:
            x: X coordinate
            y: Y coordinate
            
        Returns:
            ADBResult indicating success
        """
        logger.info("Tapping at (%d, %d)", x, y)
        return await self._run_adb("shell", "input", "tap", str(x), str(y))

    async def type_text(self, text: str) -> ADBResult:
        """
        Type text into the focused field.
        
        Note: Special characters may not work correctly. For best results,
        use simple alphanumeric text.
        
        Args:
            text: Text to type
            
        Returns:
            ADBResult indicating success
        """
        # Escape special characters for shell
        # Replace spaces with %s for ADB input
        escaped = text.replace(" ", "%s").replace("'", "\\'").replace('"', '\\"')
        logger.info("Typing text: %s", text[:50] + "..." if len(text) > 50 else text)
        return await self._run_adb("shell", "input", "text", escaped)

    async def swipe(
        self,
        direction: str,
        duration_ms: int = 300,
    ) -> ADBResult:
        """
        Swipe in a direction.
        
        Args:
            direction: One of 'up', 'down', 'left', 'right'
            duration_ms: Swipe duration in milliseconds
            
        Returns:
            ADBResult indicating success
        """
        # Screen center and swipe distances (assuming 1080x2400 screen)
        # Adjust based on your device
        cx, cy = 540, 1200
        distance = 500
        
        coords = {
            "up": (cx, cy + distance, cx, cy - distance),
            "down": (cx, cy - distance, cx, cy + distance),
            "left": (cx + distance, cy, cx - distance, cy),
            "right": (cx - distance, cy, cx + distance, cy),
        }
        
        if direction.lower() not in coords:
            return ADBResult(
                success=False,
                output="",
                error=f"Invalid direction: {direction}. Use up/down/left/right.",
            )
        
        x1, y1, x2, y2 = coords[direction.lower()]
        logger.info("Swiping %s", direction)
        return await self._run_adb(
            "shell", "input", "swipe",
            str(x1), str(y1), str(x2), str(y2), str(duration_ms)
        )

    async def press_key(self, key: str) -> ADBResult:
        """
        Press a key.
        
        Args:
            key: Key name - 'home', 'back', 'enter', 'recent', 
                 'volume_up', 'volume_down', 'power'
                 
        Returns:
            ADBResult indicating success
        """
        key_codes = {
            "home": "KEYCODE_HOME",
            "back": "KEYCODE_BACK",
            "enter": "KEYCODE_ENTER",
            "recent": "KEYCODE_APP_SWITCH",
            "volume_up": "KEYCODE_VOLUME_UP",
            "volume_down": "KEYCODE_VOLUME_DOWN",
            "power": "KEYCODE_POWER",
            "tab": "KEYCODE_TAB",
            "delete": "KEYCODE_DEL",
            "search": "KEYCODE_SEARCH",
        }
        
        keycode = key_codes.get(key.lower())
        if not keycode:
            return ADBResult(
                success=False,
                output="",
                error=f"Unknown key: {key}. Available: {', '.join(key_codes.keys())}",
            )
        
        logger.info("Pressing key: %s", key)
        return await self._run_adb("shell", "input", "keyevent", keycode)

    async def launch_app(self, package_or_name: str) -> ADBResult:
        """
        Launch an app by package name or common name.
        
        Args:
            package_or_name: Package name (com.example.app) or common name (chrome, uber)
            
        Returns:
            ADBResult indicating success
        """
        # Map common app names to package names
        app_packages = {
            "chrome": "com.android.chrome",
            "settings": "com.android.settings",
            "phone": "com.android.dialer",
            "messages": "com.google.android.apps.messaging",
            "camera": "com.android.camera",
            "photos": "com.google.android.apps.photos",
            "gmail": "com.google.android.gm",
            "maps": "com.google.android.apps.maps",
            "youtube": "com.google.android.youtube",
            "uber": "com.ubercab",
            "lyft": "me.lyft.android",
            "doordash": "com.dd.doordash",
            "ubereats": "com.ubercab.eats",
            "grubhub": "com.grubhub.android",
            "instacart": "com.instacart.client",
            "amazon": "com.amazon.mShop.android.shopping",
            "whatsapp": "com.whatsapp",
            "instagram": "com.instagram.android",
            "facebook": "com.facebook.katana",
            "twitter": "com.twitter.android",
            "x": "com.twitter.android",
            "spotify": "com.spotify.music",
            "netflix": "com.netflix.mediaclient",
            "telegram": "org.telegram.messenger",
            "discord": "com.discord",
            "slack": "com.Slack",
            "venmo": "com.venmo",
            "paypal": "com.paypal.android.p2pmobile",
            "cashapp": "com.squareup.cash",
        }
        
        # Resolve package name
        package = app_packages.get(package_or_name.lower(), package_or_name)
        
        logger.info("Launching app: %s (package: %s)", package_or_name, package)
        
        # Use monkey to launch (most reliable method)
        result = await self._run_adb(
            "shell", "monkey", "-p", package,
            "-c", "android.intent.category.LAUNCHER", "1"
        )
        
        if "No activities found" in result.output:
            # Fallback to am start
            result = await self._run_adb(
                "shell", "am", "start",
                "-a", "android.intent.action.MAIN",
                "-c", "android.intent.category.LAUNCHER",
                package
            )
        
        return result

    async def wake_device(self) -> ADBResult:
        """
        Wake the device screen if it's off.
        
        Returns:
            ADBResult indicating success
        """
        # Check if screen is on
        result = await self._run_adb(
            "shell", "dumpsys", "power", "|", "grep", "'Display Power'"
        )
        
        # Send power button if screen is off
        if "OFF" in result.output.upper():
            logger.info("Waking device")
            return await self._run_adb("shell", "input", "keyevent", "KEYCODE_WAKEUP")
        
        return ADBResult(success=True, output="Screen already on")

    async def unlock_device(self) -> ADBResult:
        """
        Attempt to unlock the device (swipe up).

        Note: This won't bypass PIN/pattern/password - device must have
        no lock screen or be set to swipe-only.

        Returns:
            ADBResult indicating success
        """
        await self.wake_device()
        # Swipe up to dismiss lock screen
        return await self.swipe("up", duration_ms=200)

    async def get_battery_level(self) -> int | None:
        """
        Get the current battery level.

        Returns:
            Battery level as percentage (0-100) or None if unavailable
        """
        result = await self._run_adb("shell", "dumpsys", "battery")
        if not result.success:
            return None

        # Parse "level: XX" from output
        for line in result.output.splitlines():
            line = line.strip()
            if line.startswith("level:"):
                try:
                    return int(line.split(":")[1].strip())
                except (ValueError, IndexError):
                    pass
        return None

    async def get_wifi_ssid(self) -> str | None:
        """
        Get the current WiFi SSID the device is connected to.

        Returns:
            WiFi SSID string or None if not connected or unavailable
        """
        result = await self._run_adb("shell", "dumpsys", "wifi")
        if not result.success:
            return None

        # Look for SSID in the output
        # Format varies by Android version, try multiple patterns
        for line in result.output.splitlines():
            line = line.strip()
            # Pattern: "SSID: MyNetwork"
            if "SSID:" in line and "null" not in line.lower():
                parts = line.split("SSID:")
                if len(parts) > 1:
                    ssid = parts[1].strip().strip('"').split(",")[0].strip()
                    if ssid and ssid != "<unknown ssid>":
                        return ssid
            # Pattern: 'mWifiInfo SSID: "MyNetwork"'
            if "mWifiInfo" in line and "SSID" in line:
                if '"' in line:
                    try:
                        ssid = line.split('"')[1]
                        if ssid and ssid != "<unknown ssid>":
                            return ssid
                    except IndexError:
                        pass
        return None

    def parse_ui_elements(self, xml_content: str) -> list[UIElement]:
        """
        Parse UI elements from accessibility XML.
        
        Args:
            xml_content: XML string from get_screen_xml()
            
        Returns:
            List of UIElement objects
        """
        elements = []
        
        # Simple regex-based parsing (avoids XML library overhead)
        node_pattern = re.compile(r'<node\s+([^>]+)/>')
        attr_pattern = re.compile(r'(\w+(?:-\w+)?)="([^"]*)"')
        bounds_pattern = re.compile(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]')
        
        for node_match in node_pattern.finditer(xml_content):
            attrs_str = node_match.group(1)
            attrs = dict(attr_pattern.findall(attrs_str))
            
            # Parse bounds
            bounds_str = attrs.get("bounds", "[0,0][0,0]")
            bounds_match = bounds_pattern.search(bounds_str)
            if bounds_match:
                bounds = tuple(int(x) for x in bounds_match.groups())
            else:
                bounds = (0, 0, 0, 0)
            
            element = UIElement(
                text=attrs.get("text", ""),
                content_desc=attrs.get("content-desc", ""),
                resource_id=attrs.get("resource-id", ""),
                class_name=attrs.get("class", ""),
                package=attrs.get("package", ""),
                bounds=bounds,
                clickable=attrs.get("clickable", "false").lower() == "true",
                scrollable=attrs.get("scrollable", "false").lower() == "true",
                focused=attrs.get("focused", "false").lower() == "true",
                enabled=attrs.get("enabled", "true").lower() == "true",
            )
            elements.append(element)
        
        return elements

    def find_element(
        self,
        elements: list[UIElement],
        *,
        text: str | None = None,
        content_desc: str | None = None,
        resource_id: str | None = None,
        class_name: str | None = None,
        clickable: bool | None = None,
    ) -> UIElement | None:
        """
        Find a UI element matching the criteria.
        
        Args:
            elements: List of UIElement to search
            text: Match by text (case-insensitive partial match)
            content_desc: Match by content description
            resource_id: Match by resource ID (partial match)
            class_name: Match by class name
            clickable: Filter by clickable status
            
        Returns:
            First matching UIElement or None
        """
        for el in elements:
            if text and text.lower() not in el.text.lower():
                continue
            if content_desc and content_desc.lower() not in el.content_desc.lower():
                continue
            if resource_id and resource_id not in el.resource_id:
                continue
            if class_name and class_name not in el.class_name:
                continue
            if clickable is not None and el.clickable != clickable:
                continue
            return el
        return None


# Singleton instance
_client: AndroidClient | None = None


def get_android_client() -> AndroidClient:
    """Get the singleton AndroidClient instance."""
    global _client
    if _client is None:
        _client = AndroidClient()
    return _client


__all__ = ["AndroidClient", "ADBResult", "UIElement", "get_android_client"]
