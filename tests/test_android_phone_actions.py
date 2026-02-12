"""
Tests for Android phone control actions.

Tests the get_screen_action and related actions for LLM-in-the-loop
phone automation.
"""

import base64
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

# Import directly from the module to avoid triggering actions/__init__.py
# which imports google auth and other heavy dependencies
sys.path.insert(0, "/home/claudia/dev/frank_bot")
from services.android_client import ADBResult, UIElement


# Sample XML that would come from uiautomator dump
SAMPLE_UI_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy>
<node bounds="[0,0][1080,2400]" class="android.widget.FrameLayout" clickable="false" content-desc="" enabled="true" focused="false" package="com.google.android.apps.nexuslauncher" resource-id="" scrollable="false" text="">
<node bounds="[0,100][1080,200]" class="android.widget.TextView" clickable="true" content-desc="" enabled="true" focused="false" package="com.google.android.apps.nexuslauncher" resource-id="com.google.android:id/title" scrollable="false" text="Settings"/>
<node bounds="[100,300][500,400]" class="android.widget.Button" clickable="true" content-desc="Navigate back" enabled="true" focused="false" package="com.google.android.apps.nexuslauncher" resource-id="com.google.android:id/back_button" scrollable="false" text="Back"/>
<node bounds="[600,300][1000,400]" class="android.widget.TextView" clickable="false" content-desc="" enabled="true" focused="false" package="com.google.android.apps.nexuslauncher" resource-id="" scrollable="false" text="Just some text"/>
</node>
</hierarchy>
"""


class TestGetScreenAction:
    """Tests for get_screen_action."""

    @pytest.mark.asyncio
    async def test_returns_screenshot_base64(self) -> None:
        """Returns base64-encoded screenshot."""
        # Create a mock PNG file content
        mock_png_data = b"\x89PNG\r\n\x1a\n" + b"fake image data"
        expected_base64 = base64.b64encode(mock_png_data).decode("utf-8")

        mock_client = MagicMock()
        mock_client.connect = AsyncMock(return_value=ADBResult(success=True, output="connected"))
        mock_client.take_screenshot = AsyncMock(return_value=ADBResult(success=True, output="/tmp/screenshot.png"))
        mock_client.get_screen_xml = AsyncMock(return_value=ADBResult(success=True, output=SAMPLE_UI_XML))
        mock_client.parse_ui_elements = MagicMock(return_value=[
            UIElement(
                text="Settings",
                content_desc="",
                resource_id="com.google.android:id/title",
                class_name="android.widget.TextView",
                package="com.google.android.apps.nexuslauncher",
                bounds=(0, 100, 1080, 200),
                clickable=True,
                scrollable=False,
                focused=False,
                enabled=True,
            )
        ])

        with patch("actions.android_phone.get_android_client", return_value=mock_client):
            with patch("builtins.open", mock_open(read_data=mock_png_data)):
                from actions.android_phone import get_screen_action

                result = await get_screen_action({})

                assert "screenshot_base64" in result
                assert result["screenshot_base64"] == expected_base64

    @pytest.mark.asyncio
    async def test_returns_raw_xml(self) -> None:
        """Returns raw accessibility XML from uiautomator dump."""
        mock_png_data = b"\x89PNG\r\n\x1a\n"

        mock_client = MagicMock()
        mock_client.connect = AsyncMock(return_value=ADBResult(success=True, output="connected"))
        mock_client.take_screenshot = AsyncMock(return_value=ADBResult(success=True, output="/tmp/screenshot.png"))
        mock_client.get_screen_xml = AsyncMock(return_value=ADBResult(success=True, output=SAMPLE_UI_XML))
        mock_client.parse_ui_elements = MagicMock(return_value=[])

        with patch("actions.android_phone.get_android_client", return_value=mock_client):
            with patch("builtins.open", mock_open(read_data=mock_png_data)):
                from actions.android_phone import get_screen_action

                result = await get_screen_action({})

                assert "xml" in result
                assert result["xml"] == SAMPLE_UI_XML

    @pytest.mark.asyncio
    async def test_returns_clickable_elements_with_required_fields(self) -> None:
        """Returns parsed list of clickable elements with all required fields."""
        mock_png_data = b"\x89PNG\r\n\x1a\n"

        mock_elements = [
            UIElement(
                text="Settings",
                content_desc="Open settings",
                resource_id="com.google.android:id/title",
                class_name="android.widget.TextView",
                package="com.google.android.apps.nexuslauncher",
                bounds=(0, 100, 1080, 200),
                clickable=True,
                scrollable=False,
                focused=False,
                enabled=True,
            ),
            UIElement(
                text="Back",
                content_desc="Navigate back",
                resource_id="com.google.android:id/back_button",
                class_name="android.widget.Button",
                package="com.google.android.apps.nexuslauncher",
                bounds=(100, 300, 500, 400),
                clickable=True,
                scrollable=False,
                focused=False,
                enabled=True,
            ),
        ]

        mock_client = MagicMock()
        mock_client.connect = AsyncMock(return_value=ADBResult(success=True, output="connected"))
        mock_client.take_screenshot = AsyncMock(return_value=ADBResult(success=True, output="/tmp/screenshot.png"))
        mock_client.get_screen_xml = AsyncMock(return_value=ADBResult(success=True, output=SAMPLE_UI_XML))
        mock_client.parse_ui_elements = MagicMock(return_value=mock_elements)

        with patch("actions.android_phone.get_android_client", return_value=mock_client):
            with patch("builtins.open", mock_open(read_data=mock_png_data)):
                from actions.android_phone import get_screen_action

                result = await get_screen_action({})

                assert "clickable_elements" in result
                elements = result["clickable_elements"]
                assert len(elements) == 2

                # Check first element has all required fields
                el = elements[0]
                assert el["text"] == "Settings"
                assert el["content_desc"] == "Open settings"
                assert el["resource_id"] == "title"  # Should strip package prefix
                assert el["center_x"] == 540  # (0 + 1080) // 2
                assert el["center_y"] == 150  # (100 + 200) // 2
                assert el["bounds"] == {"left": 0, "top": 100, "right": 1080, "bottom": 200}
                assert el["clickable"] is True

    @pytest.mark.asyncio
    async def test_includes_non_clickable_elements_with_text(self) -> None:
        """Includes elements with text even if not clickable (for context)."""
        mock_png_data = b"\x89PNG\r\n\x1a\n"

        mock_elements = [
            UIElement(
                text="Status: Online",
                content_desc="",
                resource_id="",
                class_name="android.widget.TextView",
                package="com.example",
                bounds=(0, 0, 100, 50),
                clickable=False,  # Not clickable
                scrollable=False,
                focused=False,
                enabled=True,
            ),
        ]

        mock_client = MagicMock()
        mock_client.connect = AsyncMock(return_value=ADBResult(success=True, output="connected"))
        mock_client.take_screenshot = AsyncMock(return_value=ADBResult(success=True, output="/tmp/screenshot.png"))
        mock_client.get_screen_xml = AsyncMock(return_value=ADBResult(success=True, output="<xml/>"))
        mock_client.parse_ui_elements = MagicMock(return_value=mock_elements)

        with patch("actions.android_phone.get_android_client", return_value=mock_client):
            with patch("builtins.open", mock_open(read_data=mock_png_data)):
                from actions.android_phone import get_screen_action

                result = await get_screen_action({})

                # Should include non-clickable element because it has text
                assert len(result["clickable_elements"]) == 1
                assert result["clickable_elements"][0]["text"] == "Status: Online"

    @pytest.mark.asyncio
    async def test_connection_failure_raises_error(self) -> None:
        """Raises ValueError when connection fails."""
        mock_client = MagicMock()
        mock_client.connect = AsyncMock(return_value=ADBResult(
            success=False,
            output="",
            error="Connection refused"
        ))

        with patch("actions.android_phone.get_android_client", return_value=mock_client):
            from actions.android_phone import get_screen_action

            with pytest.raises(ValueError) as exc_info:
                await get_screen_action({})

            assert "Failed to connect" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_screenshot_failure_raises_error(self) -> None:
        """Raises ValueError when screenshot capture fails."""
        mock_client = MagicMock()
        mock_client.connect = AsyncMock(return_value=ADBResult(success=True, output="connected"))
        mock_client.take_screenshot = AsyncMock(return_value=ADBResult(
            success=False,
            output="",
            error="Screen off"
        ))

        with patch("actions.android_phone.get_android_client", return_value=mock_client):
            from actions.android_phone import get_screen_action

            with pytest.raises(ValueError) as exc_info:
                await get_screen_action({})

            assert "Failed to capture screenshot" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_xml_failure_raises_error(self) -> None:
        """Raises ValueError when XML dump fails."""
        mock_png_data = b"\x89PNG\r\n\x1a\n"

        mock_client = MagicMock()
        mock_client.connect = AsyncMock(return_value=ADBResult(success=True, output="connected"))
        mock_client.take_screenshot = AsyncMock(return_value=ADBResult(success=True, output="/tmp/screenshot.png"))
        mock_client.get_screen_xml = AsyncMock(return_value=ADBResult(
            success=False,
            output="",
            error="uiautomator dump failed"
        ))

        with patch("actions.android_phone.get_android_client", return_value=mock_client):
            with patch("builtins.open", mock_open(read_data=mock_png_data)):
                from actions.android_phone import get_screen_action

                with pytest.raises(ValueError) as exc_info:
                    await get_screen_action({})

                assert "Failed to get screen XML" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_returns_element_count(self) -> None:
        """Returns total count of UI elements."""
        mock_png_data = b"\x89PNG\r\n\x1a\n"

        # Create 5 elements
        mock_elements = [
            UIElement(
                text=f"Element {i}",
                content_desc="",
                resource_id="",
                class_name="android.widget.TextView",
                package="com.example",
                bounds=(0, i * 100, 100, (i + 1) * 100),
                clickable=i % 2 == 0,
                scrollable=False,
                focused=False,
                enabled=True,
            )
            for i in range(5)
        ]

        mock_client = MagicMock()
        mock_client.connect = AsyncMock(return_value=ADBResult(success=True, output="connected"))
        mock_client.take_screenshot = AsyncMock(return_value=ADBResult(success=True, output="/tmp/screenshot.png"))
        mock_client.get_screen_xml = AsyncMock(return_value=ADBResult(success=True, output="<xml/>"))
        mock_client.parse_ui_elements = MagicMock(return_value=mock_elements)

        with patch("actions.android_phone.get_android_client", return_value=mock_client):
            with patch("builtins.open", mock_open(read_data=mock_png_data)):
                from actions.android_phone import get_screen_action

                result = await get_screen_action({})

                assert result["element_count"] == 5

    @pytest.mark.asyncio
    async def test_already_connected_succeeds(self) -> None:
        """Succeeds when device reports 'already connected'."""
        mock_png_data = b"\x89PNG\r\n\x1a\n"

        mock_client = MagicMock()
        # Connection returns success=False but says "already connected"
        mock_client.connect = AsyncMock(return_value=ADBResult(
            success=False,
            output="already connected to 10.0.0.95:5555"
        ))
        mock_client.take_screenshot = AsyncMock(return_value=ADBResult(success=True, output="/tmp/screenshot.png"))
        mock_client.get_screen_xml = AsyncMock(return_value=ADBResult(success=True, output="<xml/>"))
        mock_client.parse_ui_elements = MagicMock(return_value=[])

        with patch("actions.android_phone.get_android_client", return_value=mock_client):
            with patch("builtins.open", mock_open(read_data=mock_png_data)):
                from actions.android_phone import get_screen_action

                # Should not raise - "already connected" is acceptable
                result = await get_screen_action({})
                assert "screenshot_base64" in result


class TestAndroidPhoneHealthAction:
    """Tests for android_phone_health_action."""

    @pytest.mark.asyncio
    async def test_returns_full_health_info_when_connected(self) -> None:
        """Returns all health fields when device is connected and responding."""
        mock_client = MagicMock()
        mock_client.connect = AsyncMock(return_value=ADBResult(success=True, output="connected"))
        mock_client.check_connection = AsyncMock(return_value=True)
        mock_client.get_device_info = AsyncMock(return_value={
            "model": "Pixel 9 Pro",
            "android_version": "15",
            "build": "AP3A.240905.015"
        })
        mock_client.get_battery_level = AsyncMock(return_value=85)
        mock_client.get_wifi_ssid = AsyncMock(return_value="HomeNetwork")
        mock_client.is_wifi_enabled = AsyncMock(return_value=True)

        # Reset cache
        import actions.android_phone as ap
        ap._health_cache = None
        ap._health_cache_time = 0

        with patch("actions.android_phone.get_android_client", return_value=mock_client):
            from actions.android_phone import android_phone_health_action

            result = await android_phone_health_action({})

            assert result["connected"] is True
            assert result["device_model"] == "Pixel 9 Pro"
            assert result["android_version"] == "15"
            assert result["battery_level"] == 85
            assert result["wifi_ssid"] == "HomeNetwork"
            assert "error" not in result

    @pytest.mark.asyncio
    async def test_returns_error_when_connection_fails(self) -> None:
        """Returns connected: false with error when connection fails."""
        mock_client = MagicMock()
        mock_client.connect = AsyncMock(return_value=ADBResult(
            success=False,
            output="",
            error="Connection refused"
        ))

        # Reset cache
        import actions.android_phone as ap
        ap._health_cache = None
        ap._health_cache_time = 0

        with patch("actions.android_phone.get_android_client", return_value=mock_client):
            from actions.android_phone import android_phone_health_action

            result = await android_phone_health_action({})

            assert result["connected"] is False
            assert result["device_model"] is None
            assert "error" in result
            assert "not reachable" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_returns_error_when_device_not_responding(self) -> None:
        """Returns error when device is connected but not responding."""
        mock_client = MagicMock()
        mock_client.connect = AsyncMock(return_value=ADBResult(success=True, output="connected"))
        mock_client.check_connection = AsyncMock(return_value=False)

        # Reset cache
        import actions.android_phone as ap
        ap._health_cache = None
        ap._health_cache_time = 0

        with patch("actions.android_phone.get_android_client", return_value=mock_client):
            from actions.android_phone import android_phone_health_action

            result = await android_phone_health_action({})

            assert result["connected"] is False
            assert "error" in result
            assert "not responding" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_caches_result_for_30_seconds(self) -> None:
        """Caches health check results for 30 seconds."""
        mock_client = MagicMock()
        mock_client.connect = AsyncMock(return_value=ADBResult(success=True, output="connected"))
        mock_client.check_connection = AsyncMock(return_value=True)
        mock_client.get_device_info = AsyncMock(return_value={"model": "Pixel 9 Pro", "android_version": "15"})
        mock_client.get_battery_level = AsyncMock(return_value=85)
        mock_client.get_wifi_ssid = AsyncMock(return_value="HomeNetwork")
        mock_client.is_wifi_enabled = AsyncMock(return_value=True)

        # Reset cache
        import actions.android_phone as ap
        ap._health_cache = None
        ap._health_cache_time = 0

        with patch("actions.android_phone.get_android_client", return_value=mock_client):
            from actions.android_phone import android_phone_health_action

            # First call should hit ADB
            result1 = await android_phone_health_action({})
            assert mock_client.connect.call_count == 1

            # Second call should use cache
            result2 = await android_phone_health_action({})
            assert mock_client.connect.call_count == 1  # Still 1, used cache

            # Results should be same
            assert result1 == result2

    @pytest.mark.asyncio
    async def test_handles_none_battery_and_wifi(self) -> None:
        """Handles None values for battery and WiFi gracefully."""
        mock_client = MagicMock()
        mock_client.connect = AsyncMock(return_value=ADBResult(success=True, output="connected"))
        mock_client.check_connection = AsyncMock(return_value=True)
        mock_client.get_device_info = AsyncMock(return_value={"model": "Pixel 9 Pro", "android_version": "15"})
        mock_client.get_battery_level = AsyncMock(return_value=None)
        mock_client.get_wifi_ssid = AsyncMock(return_value=None)
        mock_client.is_wifi_enabled = AsyncMock(return_value=None)

        # Reset cache
        import actions.android_phone as ap
        ap._health_cache = None
        ap._health_cache_time = 0

        with patch("actions.android_phone.get_android_client", return_value=mock_client):
            from actions.android_phone import android_phone_health_action

            result = await android_phone_health_action({})

            assert result["connected"] is True
            assert result["battery_level"] is None
            assert result["wifi_ssid"] is None


class TestAndroidPhoneStatusAction:
    """Tests for android_phone_status_action."""

    @pytest.mark.asyncio
    async def test_returns_connected_with_device_info(self) -> None:
        """Returns connected status and device info when device responds."""
        mock_client = MagicMock()
        mock_client.device_serial = "10.0.0.95:5555"
        mock_client.connect = AsyncMock(return_value=ADBResult(success=True, output="connected"))
        mock_client.check_connection = AsyncMock(return_value=True)
        mock_client.get_device_info = AsyncMock(return_value={
            "model": "Pixel 9 Pro",
            "android_version": "15",
            "build": "AP3A.240905.015"
        })

        with patch("actions.android_phone.get_android_client", return_value=mock_client):
            from actions.android_phone import android_phone_status_action

            result = await android_phone_status_action({})

            assert result["connected"] is True
            assert result["device"] == "10.0.0.95:5555"
            assert result["model"] == "Pixel 9 Pro"
            assert result["android_version"] == "15"

    @pytest.mark.asyncio
    async def test_returns_not_connected_on_connection_failure(self) -> None:
        """Returns connected: false when connection fails."""
        mock_client = MagicMock()
        mock_client.device_serial = "10.0.0.95:5555"
        mock_client.connect = AsyncMock(return_value=ADBResult(
            success=False,
            output="",
            error="Connection refused"
        ))

        with patch("actions.android_phone.get_android_client", return_value=mock_client):
            from actions.android_phone import android_phone_status_action

            result = await android_phone_status_action({})

            assert result["connected"] is False
            assert "error" in result

    @pytest.mark.asyncio
    async def test_returns_not_connected_when_device_not_responding(self) -> None:
        """Returns connected: false when device doesn't respond to ping."""
        mock_client = MagicMock()
        mock_client.device_serial = "10.0.0.95:5555"
        mock_client.connect = AsyncMock(return_value=ADBResult(success=True, output="connected"))
        mock_client.check_connection = AsyncMock(return_value=False)

        with patch("actions.android_phone.get_android_client", return_value=mock_client):
            from actions.android_phone import android_phone_status_action

            result = await android_phone_status_action({})

            assert result["connected"] is False
            assert result["error"] == "Device not responding"


class TestThermostatSetRangeAction:
    """Tests for thermostat_set_range_action."""

    @pytest.mark.asyncio
    async def test_validates_low_temp_required(self) -> None:
        """Raises error when low_temp missing."""
        from actions.android_phone import thermostat_set_range_action

        with pytest.raises(ValueError) as exc_info:
            await thermostat_set_range_action({"high_temp": 75})

        assert "'low_temp' is required" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_validates_high_temp_required(self) -> None:
        """Raises error when high_temp missing."""
        from actions.android_phone import thermostat_set_range_action

        with pytest.raises(ValueError) as exc_info:
            await thermostat_set_range_action({"low_temp": 68})

        assert "'high_temp' is required" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_validates_temp_range_bounds(self) -> None:
        """Raises error when temps outside 50-90 range."""
        from actions.android_phone import thermostat_set_range_action

        with pytest.raises(ValueError) as exc_info:
            await thermostat_set_range_action({"low_temp": 45, "high_temp": 75})
        assert "between 50 and 90" in str(exc_info.value)

        with pytest.raises(ValueError) as exc_info:
            await thermostat_set_range_action({"low_temp": 68, "high_temp": 95})
        assert "between 50 and 90" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_validates_low_less_than_high(self) -> None:
        """Raises error when low_temp >= high_temp."""
        from actions.android_phone import thermostat_set_range_action

        with pytest.raises(ValueError) as exc_info:
            await thermostat_set_range_action({"low_temp": 75, "high_temp": 70})

        assert "must be less than" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_executes_llm_loop_and_returns_result(self) -> None:
        """Successfully executes LLM loop and sets temperature range."""
        from services.android_phone_runner import RunResult, PhoneAction
        from services.android_client import ADBResult

        mock_client = MagicMock()
        mock_client.connect = AsyncMock(return_value=ADBResult(success=True, output="connected"))
        mock_client.wake_device = AsyncMock(return_value=ADBResult(success=True, output="awake"))
        mock_client.launch_app = AsyncMock(return_value=ADBResult(success=True, output="launched"))

        mock_runner = MagicMock()
        mock_runner.is_configured = True
        mock_runner.model = "gpt-5.2"
        mock_runner.run_task = AsyncMock(return_value=RunResult(
            success=True,
            steps_taken=5,
            total_tokens_used=2500,
            total_cost=0.05,
            final_action="done",
            extracted_data={"final_low_temp": 68, "final_high_temp": 72, "mode": "heat_cool"},
            steps=[],
        ))

        with patch("actions.android_phone.get_android_client", return_value=mock_client):
            with patch("services.android_phone_runner.get_android_phone_runner", return_value=mock_runner):
                from actions.android_phone import thermostat_set_range_action

                result = await thermostat_set_range_action({"low_temp": 68, "high_temp": 72})

        assert result["success"] is True
        assert result["final_low_temp"] == 68
        assert result["final_high_temp"] == 72
        assert result["mode"] == "heat_cool"
        assert result["steps_taken"] == 5
        assert result["tokens_used"] == 2500
        mock_runner.run_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_error_on_runner_failure(self) -> None:
        """Returns error result when LLM runner fails."""
        from services.android_phone_runner import RunResult
        from services.android_client import ADBResult

        mock_client = MagicMock()
        mock_client.connect = AsyncMock(return_value=ADBResult(success=True, output="connected"))
        mock_client.wake_device = AsyncMock(return_value=ADBResult(success=True, output="awake"))
        mock_client.launch_app = AsyncMock(return_value=ADBResult(success=True, output="launched"))

        mock_runner = MagicMock()
        mock_runner.is_configured = True
        mock_runner.model = "gpt-5.2"
        mock_runner.run_task = AsyncMock(return_value=RunResult(
            success=False,
            steps_taken=10,
            total_tokens_used=5000,
            total_cost=0.10,
            error="Max steps reached",
            final_action="tap",
            extracted_data=None,
            steps=[],
        ))

        with patch("actions.android_phone.get_android_client", return_value=mock_client):
            with patch("services.android_phone_runner.get_android_phone_runner", return_value=mock_runner):
                from actions.android_phone import thermostat_set_range_action

                result = await thermostat_set_range_action({"low_temp": 68, "high_temp": 72})

        assert result["success"] is False
        assert "Max steps reached" in result["error"]
        assert result["steps_taken"] == 10

    @pytest.mark.asyncio
    async def test_raises_error_when_runner_not_configured(self) -> None:
        """Raises error when AndroidPhoneRunner not configured."""
        from services.android_client import ADBResult

        mock_client = MagicMock()
        mock_client.connect = AsyncMock(return_value=ADBResult(success=True, output="connected"))
        mock_client.wake_device = AsyncMock(return_value=ADBResult(success=True, output="awake"))
        mock_client.launch_app = AsyncMock(return_value=ADBResult(success=True, output="launched"))

        mock_runner = MagicMock()
        mock_runner.is_configured = False

        with patch("actions.android_phone.get_android_client", return_value=mock_client):
            with patch("services.android_phone_runner.get_android_phone_runner", return_value=mock_runner):
                from actions.android_phone import thermostat_set_range_action

                with pytest.raises(ValueError) as exc_info:
                    await thermostat_set_range_action({"low_temp": 68, "high_temp": 72})

                assert "not configured" in str(exc_info.value)


class TestThermostatGetStatusAction:
    """Tests for thermostat_get_status_action."""

    @pytest.mark.asyncio
    async def test_executes_llm_loop_and_extracts_status(self) -> None:
        """Successfully executes LLM loop and extracts thermostat status."""
        from services.android_phone_runner import RunResult
        from services.android_client import ADBResult

        mock_client = MagicMock()
        mock_client.connect = AsyncMock(return_value=ADBResult(success=True, output="connected"))
        mock_client.wake_device = AsyncMock(return_value=ADBResult(success=True, output="awake"))
        mock_client.launch_app = AsyncMock(return_value=ADBResult(success=True, output="launched"))

        mock_runner = MagicMock()
        mock_runner.is_configured = True
        mock_runner.model = "gpt-5.2"
        mock_runner.run_task = AsyncMock(return_value=RunResult(
            success=True,
            steps_taken=3,
            total_tokens_used=1500,
            total_cost=0.03,
            final_action="done",
            extracted_data={
                "current_temp": 72,
                "target_low": 68,
                "target_high": 74,
                "mode": "heat_cool",
                "humidity": 45,
                "status": "idle",
            },
            steps=[],
        ))

        with patch("actions.android_phone.get_android_client", return_value=mock_client):
            with patch("services.android_phone_runner.get_android_phone_runner", return_value=mock_runner):
                from actions.android_phone import thermostat_get_status_action

                result = await thermostat_get_status_action({})

        assert result["success"] is True
        assert result["current_temp"] == 72
        assert result["target_low"] == 68
        assert result["target_high"] == 74
        assert result["mode"] == "heat_cool"
        assert result["humidity"] == 45
        assert result["status"] == "idle"
        assert result["steps_taken"] == 3
        assert result["tokens_used"] == 1500

        # Verify run_task was called with correct prompt
        mock_runner.run_task.assert_called_once()
        call_kwargs = mock_runner.run_task.call_args
        assert call_kwargs.kwargs["task_prompt"] == "thermostat-getStatus"
        assert call_kwargs.kwargs["max_steps"] == 15

    @pytest.mark.asyncio
    async def test_handles_null_humidity_gracefully(self) -> None:
        """Handles case where humidity is not available."""
        from services.android_phone_runner import RunResult
        from services.android_client import ADBResult

        mock_client = MagicMock()
        mock_client.connect = AsyncMock(return_value=ADBResult(success=True, output="connected"))
        mock_client.wake_device = AsyncMock(return_value=ADBResult(success=True, output="awake"))
        mock_client.launch_app = AsyncMock(return_value=ADBResult(success=True, output="launched"))

        mock_runner = MagicMock()
        mock_runner.is_configured = True
        mock_runner.model = "gpt-5.2"
        mock_runner.run_task = AsyncMock(return_value=RunResult(
            success=True,
            steps_taken=3,
            total_tokens_used=1500,
            total_cost=0.03,
            final_action="done",
            extracted_data={
                "current_temp": 72,
                "target_low": 68,
                "target_high": 74,
                "mode": "heat_cool",
                "humidity": None,  # Not available
                "status": "heating",
            },
            steps=[],
        ))

        with patch("actions.android_phone.get_android_client", return_value=mock_client):
            with patch("services.android_phone_runner.get_android_phone_runner", return_value=mock_runner):
                from actions.android_phone import thermostat_get_status_action

                result = await thermostat_get_status_action({})

        assert result["success"] is True
        assert result["humidity"] is None  # Gracefully None
        assert result["current_temp"] == 72

    @pytest.mark.asyncio
    async def test_returns_error_when_thermostat_offline(self) -> None:
        """Returns error when LLM reports thermostat offline."""
        from services.android_phone_runner import RunResult
        from services.android_client import ADBResult

        mock_client = MagicMock()
        mock_client.connect = AsyncMock(return_value=ADBResult(success=True, output="connected"))
        mock_client.wake_device = AsyncMock(return_value=ADBResult(success=True, output="awake"))
        mock_client.launch_app = AsyncMock(return_value=ADBResult(success=True, output="launched"))

        mock_runner = MagicMock()
        mock_runner.is_configured = True
        mock_runner.model = "gpt-5.2"
        mock_runner.run_task = AsyncMock(return_value=RunResult(
            success=False,
            steps_taken=2,
            total_tokens_used=1000,
            total_cost=0.02,
            error="Thermostat is offline or unreachable",
            final_action="error",
            extracted_data=None,
            steps=[],
        ))

        with patch("actions.android_phone.get_android_client", return_value=mock_client):
            with patch("services.android_phone_runner.get_android_phone_runner", return_value=mock_runner):
                from actions.android_phone import thermostat_get_status_action

                result = await thermostat_get_status_action({})

        assert result["success"] is False
        assert "offline" in result["error"].lower() or "unreachable" in result["error"].lower()
        assert result["steps_taken"] == 2

    @pytest.mark.asyncio
    async def test_returns_error_when_google_home_fails_to_launch(self) -> None:
        """Raises error when Google Home app fails to launch."""
        from services.android_client import ADBResult

        mock_client = MagicMock()
        mock_client.connect = AsyncMock(return_value=ADBResult(success=True, output="connected"))
        mock_client.wake_device = AsyncMock(return_value=ADBResult(success=True, output="awake"))
        mock_client.launch_app = AsyncMock(return_value=ADBResult(
            success=False,
            output="",
            error="App not installed"
        ))

        with patch("actions.android_phone.get_android_client", return_value=mock_client):
            from actions.android_phone import thermostat_get_status_action

            with pytest.raises(ValueError) as exc_info:
                await thermostat_get_status_action({})

            assert "Failed to launch Google Home" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_raises_error_when_runner_not_configured(self) -> None:
        """Raises error when AndroidPhoneRunner not configured."""
        from services.android_client import ADBResult

        mock_client = MagicMock()
        mock_client.connect = AsyncMock(return_value=ADBResult(success=True, output="connected"))
        mock_client.wake_device = AsyncMock(return_value=ADBResult(success=True, output="awake"))
        mock_client.launch_app = AsyncMock(return_value=ADBResult(success=True, output="launched"))

        mock_runner = MagicMock()
        mock_runner.is_configured = False

        with patch("actions.android_phone.get_android_client", return_value=mock_client):
            with patch("services.android_phone_runner.get_android_phone_runner", return_value=mock_runner):
                from actions.android_phone import thermostat_get_status_action

                with pytest.raises(ValueError) as exc_info:
                    await thermostat_get_status_action({})

                assert "not configured" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_requires_no_parameters(self) -> None:
        """Action works with no parameters (None or empty dict)."""
        from services.android_phone_runner import RunResult
        from services.android_client import ADBResult

        mock_client = MagicMock()
        mock_client.connect = AsyncMock(return_value=ADBResult(success=True, output="connected"))
        mock_client.wake_device = AsyncMock(return_value=ADBResult(success=True, output="awake"))
        mock_client.launch_app = AsyncMock(return_value=ADBResult(success=True, output="launched"))

        mock_runner = MagicMock()
        mock_runner.is_configured = True
        mock_runner.model = "gpt-5.2"
        mock_runner.run_task = AsyncMock(return_value=RunResult(
            success=True,
            steps_taken=2,
            total_tokens_used=1000,
            total_cost=0.02,
            final_action="done",
            extracted_data={"current_temp": 70},
            steps=[],
        ))

        with patch("actions.android_phone.get_android_client", return_value=mock_client):
            with patch("services.android_phone_runner.get_android_phone_runner", return_value=mock_runner):
                from actions.android_phone import thermostat_get_status_action

                # Test with None
                result1 = await thermostat_get_status_action(None)
                assert result1["success"] is True

                # Test with empty dict
                result2 = await thermostat_get_status_action({})
                assert result2["success"] is True
