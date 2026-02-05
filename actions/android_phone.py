"""
Android phone control actions for LLM-in-the-loop automation.

Provides high-level actions for controlling an Android phone via ADB,
enabling Frank to interact with mobile apps through visual understanding
and accessibility trees.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from typing import Any

from services.android_client import get_android_client

logger = logging.getLogger(__name__)

# Cache for health check results (30 second TTL)
_health_cache: dict[str, Any] | None = None
_health_cache_time: float = 0
HEALTH_CACHE_TTL = 30  # seconds


async def get_screen_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Get the current screen state including screenshot and parsed UI elements.

    This is the foundation action for LLM-in-the-loop phone automation.
    Returns everything needed for a vision-capable LLM to understand and
    interact with the screen.

    Returns:
        screenshot_base64: Base64-encoded PNG screenshot of the current screen
        xml: Raw accessibility XML from uiautomator dump
        clickable_elements: Parsed list of clickable elements with coordinates
        element_count: Total number of UI elements on screen
    """
    client = get_android_client()

    # Ensure connected
    connect_result = await client.connect()
    if not connect_result.success and "already connected" not in connect_result.output.lower():
        raise ValueError(f"Failed to connect to device: {connect_result.error}")

    # Get screenshot as base64
    screenshot_result = await client.take_screenshot()
    if not screenshot_result.success:
        raise ValueError(f"Failed to capture screenshot: {screenshot_result.error}")

    # Read the screenshot file and encode as base64
    screenshot_path = screenshot_result.output
    try:
        with open(screenshot_path, "rb") as f:
            screenshot_bytes = f.read()
        screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")
    except Exception as exc:
        raise ValueError(f"Failed to read screenshot file: {exc}") from exc

    # Get accessibility XML
    xml_result = await client.get_screen_xml()
    if not xml_result.success:
        raise ValueError(f"Failed to get screen XML: {xml_result.error}")

    raw_xml = xml_result.output

    # Parse UI elements
    elements = client.parse_ui_elements(raw_xml)

    # Build clickable elements list with required fields
    clickable_elements = []
    for el in elements:
        # Include elements that are clickable OR have text/content_desc (for visibility)
        if el.clickable or el.text or el.content_desc:
            element_info = {
                "text": el.text,
                "content_desc": el.content_desc,
                "resource_id": el.resource_id.split("/")[-1] if "/" in el.resource_id else el.resource_id,
                "center_x": el.center[0],
                "center_y": el.center[1],
                "bounds": {
                    "left": el.bounds[0],
                    "top": el.bounds[1],
                    "right": el.bounds[2],
                    "bottom": el.bounds[3],
                },
                "clickable": el.clickable,
                "class_name": el.class_name.split(".")[-1] if "." in el.class_name else el.class_name,
            }
            clickable_elements.append(element_info)

    return {
        "screenshot_base64": screenshot_base64,
        "xml": raw_xml,
        "clickable_elements": clickable_elements,
        "element_count": len(elements),
        "message": f"Screen captured with {len(clickable_elements)} interactive elements",
    }


async def android_phone_health_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Health check for Android phone connection.

    Returns device connection status, model, Android version, battery level,
    and WiFi SSID. Results are cached for 30 seconds to reduce ADB overhead.

    This endpoint can be called without API key for status monitoring.

    Returns:
        connected: Whether the device is reachable
        device_model: Device model name (e.g., "Pixel 9 Pro")
        android_version: Android OS version (e.g., "15")
        battery_level: Battery percentage (0-100)
        wifi_ssid: Current WiFi network name
        error: Error message if device not reachable
    """
    global _health_cache, _health_cache_time

    # Check cache
    current_time = time.time()
    if _health_cache is not None and (current_time - _health_cache_time) < HEALTH_CACHE_TTL:
        return _health_cache

    client = get_android_client()

    # Try to connect
    connect_result = await client.connect()

    if not connect_result.success and "already connected" not in connect_result.output.lower():
        result = {
            "connected": False,
            "device_model": None,
            "android_version": None,
            "battery_level": None,
            "wifi_ssid": None,
            "error": f"Device not reachable: {connect_result.error or 'Connection failed'}",
        }
        _health_cache = result
        _health_cache_time = current_time
        return result

    # Check if device is responding
    is_connected = await client.check_connection()

    if not is_connected:
        result = {
            "connected": False,
            "device_model": None,
            "android_version": None,
            "battery_level": None,
            "wifi_ssid": None,
            "error": "Device connected but not responding",
        }
        _health_cache = result
        _health_cache_time = current_time
        return result

    # Get device info
    device_info = await client.get_device_info()

    # Get battery level
    battery_level = await client.get_battery_level()

    # Get WiFi SSID
    wifi_ssid = await client.get_wifi_ssid()

    result = {
        "connected": True,
        "device_model": device_info.get("model"),
        "android_version": device_info.get("android_version"),
        "battery_level": battery_level,
        "wifi_ssid": wifi_ssid,
    }

    _health_cache = result
    _health_cache_time = current_time

    return result


async def android_phone_status_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Get the status of the Android phone connection.

    Returns device info if connected, or connection error details.
    """
    client = get_android_client()

    # Try to connect
    connect_result = await client.connect()

    if not connect_result.success and "already connected" not in connect_result.output.lower():
        return {
            "connected": False,
            "device": client.device_serial,
            "error": connect_result.error,
        }

    # Check if actually responding
    is_connected = await client.check_connection()

    if not is_connected:
        return {
            "connected": False,
            "device": client.device_serial,
            "error": "Device not responding",
        }

    # Get device info
    device_info = await client.get_device_info()

    return {
        "connected": True,
        "device": client.device_serial,
        "model": device_info.get("model", "Unknown"),
        "android_version": device_info.get("android_version", "Unknown"),
        "build": device_info.get("build", "Unknown"),
    }


async def android_phone_screen_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Get the current screen state as a structured representation.

    Returns the UI accessibility tree which shows all visible elements,
    their text, positions, and whether they're clickable.

    This is the primary way to understand what's on the device screen.
    """
    args = arguments or {}
    include_raw_xml = args.get("include_xml", False)

    client = get_android_client()

    # Ensure connected
    await client.connect()

    # Get screen XML
    result = await client.get_screen_xml()

    if not result.success:
        raise ValueError(f"Failed to get screen: {result.error}")

    # Parse elements
    elements = client.parse_ui_elements(result.output)

    # Build structured response
    clickable_elements = []
    text_elements = []

    for el in elements:
        el_info = {
            "text": el.text,
            "content_desc": el.content_desc,
            "resource_id": el.resource_id.split("/")[-1] if "/" in el.resource_id else el.resource_id,
            "center_x": el.center[0],
            "center_y": el.center[1],
        }

        if el.clickable and (el.text or el.content_desc):
            clickable_elements.append(el_info)
        elif el.text:
            text_elements.append(el_info)

    response = {
        "total_elements": len(elements),
        "clickable_elements": clickable_elements[:50],  # Limit for readability
        "text_elements": text_elements[:30],
        "hint": "Use tap action with center_x and center_y coordinates to interact with elements",
    }

    if include_raw_xml:
        response["raw_xml"] = result.output

    return response


async def android_phone_tap_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Tap at specific coordinates on the Android screen.

    Args:
        x: X coordinate to tap
        y: Y coordinate to tap

    Use the screen action first to find element coordinates.
    """
    args = arguments or {}

    x = args.get("x")
    y = args.get("y")

    if x is None or y is None:
        raise ValueError("Both 'x' and 'y' coordinates are required")

    try:
        x = int(x)
        y = int(y)
    except (ValueError, TypeError):
        raise ValueError("Coordinates must be integers")

    client = get_android_client()
    await client.connect()

    result = await client.tap(x, y)

    if not result.success:
        raise ValueError(f"Tap failed: {result.error}")

    return {
        "success": True,
        "action": "tap",
        "x": x,
        "y": y,
        "message": f"Tapped at ({x}, {y})",
    }


async def android_phone_type_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Type text into the currently focused field.

    Make sure to tap on a text field first to focus it before typing.

    Args:
        text: The text to type
    """
    args = arguments or {}
    text = args.get("text", "")

    if not text:
        raise ValueError("'text' is required")

    client = get_android_client()
    await client.connect()

    result = await client.type_text(text)

    if not result.success:
        raise ValueError(f"Type failed: {result.error}")

    return {
        "success": True,
        "action": "type",
        "text": text[:50] + "..." if len(text) > 50 else text,
        "message": "Typed text into focused field",
    }


async def android_phone_swipe_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Swipe in a direction on the screen.

    Useful for scrolling lists, dismissing screens, or navigating.

    Args:
        direction: One of 'up', 'down', 'left', 'right'
    """
    args = arguments or {}
    direction = args.get("direction", "").lower()

    valid_directions = ["up", "down", "left", "right"]
    if direction not in valid_directions:
        raise ValueError(f"'direction' must be one of: {', '.join(valid_directions)}")

    client = get_android_client()
    await client.connect()

    result = await client.swipe(direction)

    if not result.success:
        raise ValueError(f"Swipe failed: {result.error}")

    return {
        "success": True,
        "action": "swipe",
        "direction": direction,
        "message": f"Swiped {direction}",
    }


async def android_phone_key_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Press a key on the device.

    Args:
        key: Key name - 'home', 'back', 'enter', 'recent',
             'volume_up', 'volume_down', 'power', 'tab', 'delete'
    """
    args = arguments or {}
    key = args.get("key", "").lower()

    valid_keys = ["home", "back", "enter", "recent", "volume_up", "volume_down", "power", "tab", "delete", "search"]
    if key not in valid_keys:
        raise ValueError(f"'key' must be one of: {', '.join(valid_keys)}")

    client = get_android_client()
    await client.connect()

    result = await client.press_key(key)

    if not result.success:
        raise ValueError(f"Key press failed: {result.error}")

    return {
        "success": True,
        "action": "key",
        "key": key,
        "message": f"Pressed {key} key",
    }


async def android_phone_launch_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Launch an app on the Android device.

    Args:
        app: App name (e.g., 'uber', 'doordash', 'chrome') or
             package name (e.g., 'com.ubercab')

    Supported app names: uber, lyft, doordash, ubereats, grubhub, instacart,
    chrome, settings, maps, youtube, whatsapp, instagram, venmo, cashapp, etc.
    """
    args = arguments or {}
    app = args.get("app", "").strip()

    if not app:
        raise ValueError("'app' is required (app name or package name)")

    client = get_android_client()
    await client.connect()

    result = await client.launch_app(app)

    if not result.success:
        raise ValueError(f"Failed to launch app: {result.error}")

    # Wait a moment for app to start
    await asyncio.sleep(1)

    return {
        "success": True,
        "action": "launch",
        "app": app,
        "message": f"Launched {app}",
        "hint": "Use the screen action to see what's displayed in the app",
    }


async def android_phone_wake_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Wake up the device screen if it's off.

    Call this before other actions if the device may have gone to sleep.
    """
    client = get_android_client()
    await client.connect()

    result = await client.wake_device()

    if not result.success:
        raise ValueError(f"Wake failed: {result.error}")

    return {
        "success": True,
        "action": "wake",
        "message": result.output,
    }


async def android_phone_screenshot_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Take a screenshot of the device screen.

    Useful for visual verification when the UI XML doesn't provide
    enough context (e.g., images, colors, complex layouts).

    Returns the path to the saved screenshot.
    """
    client = get_android_client()
    await client.connect()

    result = await client.take_screenshot()

    if not result.success:
        raise ValueError(f"Screenshot failed: {result.error}")

    return {
        "success": True,
        "action": "screenshot",
        "path": result.output,
        "message": f"Screenshot saved to {result.output}",
    }


async def android_phone_find_and_tap_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Find an element by text and tap it.

    This is a convenience action that combines screen reading and tapping.

    Args:
        text: Text to search for (case-insensitive partial match)
        content_desc: Alternative: search by content description
    """
    args = arguments or {}
    text = args.get("text", "")
    content_desc = args.get("content_desc", "")

    if not text and not content_desc:
        raise ValueError("Either 'text' or 'content_desc' is required")

    client = get_android_client()
    await client.connect()

    # Get screen
    result = await client.get_screen_xml()
    if not result.success:
        raise ValueError(f"Failed to read screen: {result.error}")

    # Parse and find element
    elements = client.parse_ui_elements(result.output)
    element = client.find_element(
        elements,
        text=text if text else None,
        content_desc=content_desc if content_desc else None,
        clickable=True,
    )

    if not element:
        # Try without clickable filter
        element = client.find_element(
            elements,
            text=text if text else None,
            content_desc=content_desc if content_desc else None,
        )

    if not element:
        search_term = text or content_desc
        raise ValueError(f"Could not find element matching '{search_term}'")

    # Tap the element
    x, y = element.center
    tap_result = await client.tap(x, y)

    if not tap_result.success:
        raise ValueError(f"Tap failed: {tap_result.error}")

    return {
        "success": True,
        "action": "find_and_tap",
        "found_text": element.text or element.content_desc,
        "x": x,
        "y": y,
        "message": f"Found and tapped '{element.text or element.content_desc}' at ({x}, {y})",
    }


# Temperature validation bounds
MIN_TEMP_F = 50
MAX_TEMP_F = 90


async def thermostat_set_range_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Set the thermostat temperature range via Google Home app.

    This action uses LLM-in-the-loop automation to navigate the Google Home
    app and set the thermostat to the specified temperature range.

    Args:
        low_temp: Target low temperature (heat setpoint) in Fahrenheit (50-90)
        high_temp: Target high temperature (cool setpoint) in Fahrenheit (50-90)

    Returns:
        success: Whether the operation completed successfully
        final_low_temp: The actual low temperature set
        final_high_temp: The actual high temperature set
        steps_taken: Number of automation steps executed
        tokens_used: LLM tokens consumed
        estimated_cost: Estimated cost in USD
    """
    from services.android_phone_runner import get_android_phone_runner

    args = arguments or {}

    # Validate low_temp
    low_temp = args.get("low_temp")
    if low_temp is None:
        raise ValueError("'low_temp' is required")
    try:
        low_temp = int(low_temp)
    except (ValueError, TypeError):
        raise ValueError("'low_temp' must be an integer")
    if low_temp < MIN_TEMP_F or low_temp > MAX_TEMP_F:
        raise ValueError(f"'low_temp' must be between {MIN_TEMP_F} and {MAX_TEMP_F}")

    # Validate high_temp
    high_temp = args.get("high_temp")
    if high_temp is None:
        raise ValueError("'high_temp' is required")
    try:
        high_temp = int(high_temp)
    except (ValueError, TypeError):
        raise ValueError("'high_temp' must be an integer")
    if high_temp < MIN_TEMP_F or high_temp > MAX_TEMP_F:
        raise ValueError(f"'high_temp' must be between {MIN_TEMP_F} and {MAX_TEMP_F}")

    # Validate range
    if low_temp >= high_temp:
        raise ValueError("'low_temp' must be less than 'high_temp'")

    # Launch Google Home app first
    client = get_android_client()
    await client.connect()
    await client.wake_device()
    launch_result = await client.launch_app("com.google.android.apps.chromecast.app")
    if not launch_result.success:
        raise ValueError(f"Failed to launch Google Home: {launch_result.error}")

    # Wait for app to load
    await asyncio.sleep(2)

    # Run the automation
    runner = get_android_phone_runner()

    if not runner.is_configured:
        raise ValueError(
            "AndroidPhoneRunner not configured. "
            "Set ANDROID_LLM_MODEL and ANDROID_LLM_API_KEY environment variables."
        )

    logger.info(
        "Starting thermostat set range: low=%d, high=%d, model=%s",
        low_temp, high_temp, runner.model,
    )

    result = await runner.run_task(
        task_prompt="thermostat-setRange",
        parameters={"low_temp": low_temp, "high_temp": high_temp},
        max_steps=20,
    )

    if not result.success:
        return {
            "success": False,
            "error": result.error,
            "steps_taken": result.steps_taken,
            "tokens_used": result.total_tokens_used,
            "estimated_cost": result.total_cost,
        }

    # Extract final temperatures from result
    extracted = result.extracted_data or {}

    return {
        "success": True,
        "final_low_temp": extracted.get("final_low_temp", low_temp),
        "final_high_temp": extracted.get("final_high_temp", high_temp),
        "mode": extracted.get("mode", "heat_cool"),
        "steps_taken": result.steps_taken,
        "tokens_used": result.total_tokens_used,
        "estimated_cost": result.total_cost,
        "message": f"Thermostat set to {low_temp}-{high_temp}°F",
    }


async def thermostat_get_status_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Get the current thermostat status via Google Home app.

    This action uses LLM-in-the-loop automation to navigate the Google Home
    app and read the current thermostat status.

    Returns:
        success: Whether the operation completed successfully
        current_temp: Current ambient temperature in °F
        target_low: Heat setpoint in °F
        target_high: Cool setpoint in °F
        mode: Current mode (heat, cool, heat_cool, eco, off)
        humidity: Humidity percentage if available
        status: Current status (heating, cooling, idle, off)
        steps_taken: Number of automation steps executed
        tokens_used: LLM tokens consumed
        estimated_cost: Estimated cost in USD
    """
    from services.android_phone_runner import get_android_phone_runner

    # Launch Google Home app first
    client = get_android_client()
    await client.connect()
    await client.wake_device()
    launch_result = await client.launch_app("com.google.android.apps.chromecast.app")
    if not launch_result.success:
        raise ValueError(f"Failed to launch Google Home: {launch_result.error}")

    # Wait for app to load
    await asyncio.sleep(2)

    # Run the automation
    runner = get_android_phone_runner()

    if not runner.is_configured:
        raise ValueError(
            "AndroidPhoneRunner not configured. "
            "Set ANDROID_LLM_MODEL and ANDROID_LLM_API_KEY environment variables."
        )

    logger.info("Starting thermostat status read, model=%s", runner.model)

    result = await runner.run_task(
        task_prompt="thermostat-getStatus",
        parameters={},
        max_steps=15,  # Status read should be simpler than set
    )

    if not result.success:
        return {
            "success": False,
            "error": result.error,
            "steps_taken": result.steps_taken,
            "tokens_used": result.total_tokens_used,
            "estimated_cost": result.total_cost,
        }

    # Extract status from result
    extracted = result.extracted_data or {}

    return {
        "success": True,
        "current_temp": extracted.get("current_temp"),
        "target_low": extracted.get("target_low"),
        "target_high": extracted.get("target_high"),
        "mode": extracted.get("mode"),
        "humidity": extracted.get("humidity"),
        "status": extracted.get("status"),
        "steps_taken": result.steps_taken,
        "tokens_used": result.total_tokens_used,
        "estimated_cost": result.total_cost,
    }


async def android_phone_audit_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Get recent Android phone audit log entries.

    Returns the most recent actions logged, optionally filtered by action type.

    Args:
        limit: Maximum number of entries to return (default 100, max 500)
        action: Optional filter by action name

    Returns:
        entries: List of audit log entries (most recent first)
        stats: Aggregate statistics about actions
    """
    from services.android_audit import get_android_audit_logger

    args = arguments or {}

    limit = int(args.get("limit", 100))
    # Cap at 500 to prevent huge responses
    limit = min(limit, 500)

    action_filter = args.get("action")

    audit_logger = get_android_audit_logger()

    entries = audit_logger.get_recent_entries(
        limit=limit,
        action_filter=action_filter,
    )

    stats = audit_logger.get_stats()

    return {
        "entries": entries,
        "count": len(entries),
        "stats": stats,
    }


__all__ = [
    "get_screen_action",
    "android_phone_health_action",
    "android_phone_status_action",
    "android_phone_screen_action",
    "android_phone_tap_action",
    "android_phone_type_action",
    "android_phone_swipe_action",
    "android_phone_key_action",
    "android_phone_launch_action",
    "android_phone_wake_action",
    "android_phone_screenshot_action",
    "android_phone_find_and_tap_action",
    "thermostat_set_range_action",
    "thermostat_get_status_action",
    "android_phone_audit_action",
]
