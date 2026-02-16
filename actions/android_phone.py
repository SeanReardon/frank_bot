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
            "transport": "usb" if client.is_usb else "tcp",
            "device_serial": client.device_serial,
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
            "transport": "usb" if client.is_usb else "tcp",
            "device_serial": client.device_serial,
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

    # Get WiFi state
    wifi_enabled = await client.is_wifi_enabled()
    wifi_ssid = await client.get_wifi_ssid()

    result = {
        "connected": True,
        "transport": "usb" if client.is_usb else "tcp",
        "device_serial": client.device_serial,
        "device_model": device_info.get("model"),
        "android_version": device_info.get("android_version"),
        "battery_level": battery_level,
        "wifi_enabled": wifi_enabled,
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


async def update_apps_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Check for and install app updates via Play Store.

    This action launches the Play Store and provides instructions for
    completing the update process via LLM automation.

    Returns:
        success: Whether the operation initiated successfully
        requires_llm_automation: True if LLM automation is needed to complete
        workflow: Steps to complete the update process
    """
    from services.android_maintenance import get_android_maintenance_service

    maintenance = get_android_maintenance_service()

    # First check for updates
    check_result = await maintenance.check_app_updates()

    if not check_result.success:
        return {
            "success": False,
            "error": check_result.error,
            "message": check_result.message,
        }

    # Then initiate updates
    update_result = await maintenance.install_app_updates()

    return {
        "success": update_result.success,
        "message": update_result.message,
        "requires_llm_automation": update_result.details.get("requires_llm_automation", True)
        if update_result.details
        else True,
        "workflow": update_result.details.get("workflow", []) if update_result.details else [],
        "hint": "Use LLM automation with maintenance-updateApps prompt to complete this task",
    }


async def check_security_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Check the device's current security patch level.

    Returns:
        success: Whether the check completed successfully
        security_patch: Current security patch date (e.g., "2025-01-05")
        android_version: Android OS version
        build_date: Device build date
    """
    from services.android_maintenance import get_android_maintenance_service

    maintenance = get_android_maintenance_service()
    result = await maintenance.check_security_patch()

    if not result.success:
        return {
            "success": False,
            "error": result.error,
            "message": result.message,
        }

    return {
        "success": True,
        "message": result.message,
        "security_patch": result.details.get("security_patch") if result.details else None,
        "android_version": result.details.get("android_version") if result.details else None,
        "build_date": result.details.get("build_date") if result.details else None,
        "note": result.details.get("note") if result.details else None,
    }


async def reboot_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Reboot the Android device.

    This action requires explicit confirmation to prevent accidental reboots.

    Args:
        confirm: Must be "true" to actually perform the reboot

    Returns:
        success: Whether the reboot was initiated
        message: Status message
    """
    from services.android_maintenance import get_android_maintenance_service

    args = arguments or {}
    confirm_str = str(args.get("confirm", "")).lower()
    confirm = confirm_str in ("true", "1", "yes")

    maintenance = get_android_maintenance_service()
    result = await maintenance.reboot_device(confirm=confirm)

    response: dict[str, Any] = {
        "success": result.success,
        "message": result.message,
    }

    if result.error:
        response["error"] = result.error

    if result.details:
        response.update(result.details)

    return response


async def get_storage_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Get device storage information.

    Returns:
        success: Whether the check completed successfully
        used_percent: Percentage of storage used
        free_percent: Percentage of storage free
        total_formatted: Total storage in human-readable format
        used_formatted: Used storage in human-readable format
        free_formatted: Free storage in human-readable format
    """
    from services.android_maintenance import get_android_maintenance_service

    maintenance = get_android_maintenance_service()
    result = await maintenance.get_storage_info()

    if not result.success:
        return {
            "success": False,
            "error": result.error,
            "message": result.message,
        }

    return {
        "success": True,
        "message": result.message,
        **(result.details or {}),
    }


async def clear_cache_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Clear app caches if storage is low.

    Args:
        threshold: Storage used percentage threshold (default 90)

    Returns:
        success: Whether the operation completed
        action_taken: Whether caches were actually cleared
        storage_used_percent: Current storage usage before clearing
    """
    from services.android_maintenance import get_android_maintenance_service

    args = arguments or {}
    threshold = float(args.get("threshold", 90.0))

    maintenance = get_android_maintenance_service()
    result = await maintenance.clear_caches(threshold_percent=threshold)

    if not result.success:
        return {
            "success": False,
            "error": result.error,
            "message": result.message,
        }

    return {
        "success": True,
        "message": result.message,
        **(result.details or {}),
    }


async def battery_health_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Get detailed battery health information.

    Returns:
        success: Whether the check completed successfully
        level_percent: Current battery level
        health: Battery health status
        temperature: Battery temperature
        plugged: Whether device is plugged in
    """
    from services.android_maintenance import get_android_maintenance_service

    maintenance = get_android_maintenance_service()
    result = await maintenance.get_battery_health()

    if not result.success:
        return {
            "success": False,
            "error": result.error,
            "message": result.message,
        }

    details = result.details or {}
    # Don't include raw_info in the response to keep it concise
    return {
        "success": True,
        "message": result.message,
        "level_percent": details.get("level_percent"),
        "status": details.get("status"),
        "health": details.get("health"),
        "temperature": details.get("temperature"),
        "plugged": details.get("plugged"),
    }


# App package mapping (shared by task functions)
APP_PACKAGES = {
    "google_home": "com.google.android.apps.chromecast.app",
    "uber": "com.ubercab",
    "lyft": "com.lyft.android",
    "doordash": "com.dd.doordash",
    "uber_eats": "com.ubercab.eats",
    "chrome": "com.android.chrome",
    "maps": "com.google.android.apps.maps",
    "settings": "com.android.settings",
}


def _detect_app_from_goal(goal: str) -> str | None:
    """Auto-detect which app to launch based on the goal description."""
    goal_lower = goal.lower()
    if any(word in goal_lower for word in ["thermostat", "temperature", "hvac", "heat", "cool", "nest"]):
        return "google_home"
    elif any(word in goal_lower for word in ["light", "lamp", "switch", "plug", "smart home"]):
        return "google_home"
    elif "uber" in goal_lower and "eats" not in goal_lower:
        return "uber"
    elif "lyft" in goal_lower:
        return "lyft"
    elif any(word in goal_lower for word in ["doordash", "food delivery"]):
        return "doordash"
    elif "uber eats" in goal_lower:
        return "uber_eats"
    elif any(word in goal_lower for word in ["map", "direction", "navigate"]):
        return "maps"
    elif any(word in goal_lower for word in ["search", "browse", "website", "google"]):
        return "chrome"
    return None


async def _execute_task_background(task_id: str, goal: str, app: str | None) -> None:
    """Execute a task in the background. Updates task storage with progress."""
    from services.android_phone_runner import get_android_phone_runner
    from services.android_task_storage import get_android_task_storage

    storage = get_android_task_storage()

    try:
        # Mark as running
        await storage.update_task(task_id, status="running", current_step="Initializing")

        # Check for cancellation
        if storage.is_cancel_requested(task_id):
            return

        # Connect and wake device
        client = get_android_client()
        await client.connect()
        await client.wake_device()

        await storage.update_task(task_id, current_step="Device ready")

        # Check for cancellation
        if storage.is_cancel_requested(task_id):
            return

        # Launch app if specified
        if app and app in APP_PACKAGES:
            package = APP_PACKAGES[app]
            await storage.update_task(task_id, current_step=f"Launching {app}")
            launch_result = await client.launch_app(package)
            if not launch_result.success:
                logger.warning("Failed to launch %s: %s", app, launch_result.error)
            await asyncio.sleep(2)  # Wait for app to load

        # Check for cancellation
        if storage.is_cancel_requested(task_id):
            return

        # Run the automation
        runner = get_android_phone_runner()

        if not runner.is_configured:
            await storage.update_task(
                task_id,
                status="failed",
                error="AndroidPhoneRunner not configured. Set ANDROID_LLM_MODEL and ANDROID_LLM_API_KEY.",
            )
            return

        await storage.update_task(task_id, current_step="Running automation")
        logger.info("Task %s: Starting automation for goal: %s", task_id, goal[:50])

        result = await runner.run_task(
            task_prompt="_generic",
            parameters={"GOAL": goal},
            max_steps=25,
        )

        # Update with final result
        if result.success:
            extracted = result.extracted_data or {}
            await storage.update_task(
                task_id,
                status="completed",
                result={
                    "success": True,
                    "result": extracted.get("result", "Task completed"),
                    "extracted_data": extracted.get("extracted_data", extracted),
                },
                steps_taken=result.steps_taken,
                tokens_used=result.total_tokens_used,
                estimated_cost=result.total_cost,
                current_step=None,
            )
            logger.info("Task %s: Completed successfully", task_id)
        else:
            await storage.update_task(
                task_id,
                status="failed",
                error=result.error,
                steps_taken=result.steps_taken,
                tokens_used=result.total_tokens_used,
                estimated_cost=result.total_cost,
                current_step=None,
            )
            logger.info("Task %s: Failed - %s", task_id, result.error)

    except asyncio.CancelledError:
        await storage.update_task(task_id, status="cancelled", error="Task was cancelled")
        logger.info("Task %s: Cancelled", task_id)
    except Exception as exc:
        logger.exception("Task %s: Unexpected error", task_id)
        await storage.update_task(task_id, status="failed", error=str(exc))
    finally:
        storage.unregister_future(task_id)


async def task_do_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Start a goal-based task on the Android phone (async - returns immediately).

    Describe what you want to accomplish in natural language. The task runs in
    the background and you can check status with androidPhoneTaskGet.

    IMPORTANT: The automation will STOP before any irreversible actions like
    payments, purchases, or bookings - returning details for human review.

    Args:
        goal: Natural language description of what to accomplish.
              Examples:
              - "Check the thermostat temperature and humidity"
              - "Set the thermostat to 65-70 degrees"
              - "Open Uber and check ride prices to SFO airport"
              - "Turn off the living room lights"
        app: (Optional) App to launch first. Auto-detected from goal if omitted.

    Returns:
        task_id: ID to use with androidPhoneTaskGet/Cancel
        status: "pending" (task is queued to start)
        goal: Echo of the goal
        message: Instructions for checking status

    Use androidPhoneTaskGet(task_id) to check progress and get results.
    Use androidPhoneTaskCancel(task_id) to cancel a running task.
    """
    from services.android_task_storage import get_android_task_storage

    args = arguments or {}

    goal = args.get("goal", "").strip()
    if not goal:
        raise ValueError("'goal' is required - describe what you want to accomplish")

    app = args.get("app", "").strip().lower() if args.get("app") else None

    # Auto-detect app from goal if not specified
    if not app:
        app = _detect_app_from_goal(goal)

    # Create task record
    storage = get_android_task_storage()
    task = await storage.create_task(goal=goal, app=app)

    # Start background execution
    future = asyncio.create_task(_execute_task_background(task.id, goal, app))
    storage.register_future(task.id, future)

    logger.info("Created async task %s: %s (app=%s)", task.id, goal[:50], app or "auto")

    return {
        "task_id": task.id,
        "status": "pending",
        "goal": goal,
        "app": app,
        "message": f"Task started. Check status with androidPhoneTaskGet(task_id='{task.id}')",
    }


async def task_get_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Get the status and result of an Android phone task.

    Args:
        task_id: The task ID returned by androidPhoneTaskDo

    Returns:
        Task details including status, progress, and results (if completed).
        Status values: pending, running, completed, failed, cancelled
    """
    from services.android_task_storage import get_android_task_storage

    args = arguments or {}
    task_id = args.get("task_id", "").strip()

    if not task_id:
        raise ValueError("'task_id' is required")

    storage = get_android_task_storage()
    task = await storage.get_task(task_id)

    if not task:
        raise ValueError(f"Task '{task_id}' not found")

    return task.to_dict()


async def task_list_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    List recent Android phone tasks.

    Args:
        status: Filter by status (pending, running, completed, failed, cancelled, active)
                'active' returns pending + running tasks
        limit: Maximum number of tasks to return (default 20)

    Returns:
        tasks: List of task summaries (most recent first)
        count: Number of tasks returned
    """
    from services.android_task_storage import get_android_task_storage

    args = arguments or {}
    status = args.get("status", "").strip() or None
    limit = int(args.get("limit", 20))

    storage = get_android_task_storage()
    tasks = await storage.list_tasks(status=status, limit=limit)

    return {
        "tasks": [t.to_summary() for t in tasks],
        "count": len(tasks),
    }


async def task_cancel_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Cancel a running Android phone task.

    Args:
        task_id: The task ID to cancel

    Returns:
        Task details after cancellation.
        Note: Already completed/failed tasks cannot be cancelled.
    """
    from services.android_task_storage import get_android_task_storage

    args = arguments or {}
    task_id = args.get("task_id", "").strip()

    if not task_id:
        raise ValueError("'task_id' is required")

    storage = get_android_task_storage()
    task = await storage.cancel_task(task_id)

    if not task:
        raise ValueError(f"Task '{task_id}' not found")

    if task.status in ("completed", "failed"):
        return {
            "message": f"Task already {task.status}, cannot cancel",
            **task.to_dict(),
        }

    return {
        "message": "Task cancelled",
        **task.to_dict(),
    }


# Keep old name as alias for backwards compatibility
async def do_task_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Alias for task_do_action for backwards compatibility."""
    return await task_do_action(arguments)


async def api_learn_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Learn the full capabilities of the Android phone automation system.

    Call this FIRST before using androidPhoneTaskDo. Returns comprehensive
    documentation about everything the phone can do, including:
    - Smart home control (thermostat, lights, locks, cameras)
    - Ride services (Uber, Lyft - price checks, booking)
    - Food delivery (DoorDash, Uber Eats - browsing, ordering)
    - Device maintenance (storage, battery, updates, reboot)
    - Browser and general app navigation

    The androidPhoneTaskDo endpoint accepts natural language goals and
    accomplishes them through LLM-in-the-loop visual automation.

    Returns:
        capabilities: Comprehensive list of what can be done with examples
        supported_apps: Apps that can be controlled
        safety_rules: Actions that require human confirmation
        cost_estimates: Token usage and cost by task type
        maintenance_tasks: Device maintenance operations available
        tips: Best practices for effective goal descriptions
    """
    return {
        "overview": (
            "Sean's Pixel 9 Pro is available for automation via androidPhoneTaskDo. "
            "Describe ANY goal in natural language - the system uses vision + UI automation "
            "to accomplish it. This endpoint replaces dozens of specialized APIs with one "
            "universal interface. Call androidPhoneTaskDo with a 'goal' parameter."
        ),
        "how_it_works": [
            "1. You describe what you want in the 'goal' parameter",
            "2. System wakes phone, launches relevant app (auto-detected or specified)",
            "3. LLM sees screenshot + clickable elements",
            "4. LLM decides action: tap(x,y), type(text), swipe(direction), etc.",
            "5. Action executes, new screenshot captured, loop continues",
            "6. Returns extracted data OR stops for confirmation at payment/booking",
        ],
        "capabilities": {
            "thermostat_control": {
                "description": "Full Nest thermostat control via Google Home app",
                "what_you_can_do": [
                    "Read current temperature and humidity",
                    "Read heat/cool setpoints",
                    "Set temperature range (e.g., 65-70°F)",
                    "Check if heating or cooling is active",
                    "See thermostat mode (heat, cool, heat_cool, eco, off)",
                ],
                "example_goals": [
                    "Check the thermostat - what's the current temp and humidity?",
                    "Set the thermostat to heat between 68 and 72 degrees",
                    "Is the AC running right now?",
                    "What's the Nest set to?",
                ],
            },
            "smart_home": {
                "description": "Control all Google Home-connected devices",
                "what_you_can_do": [
                    "Turn lights on/off",
                    "Dim lights to specific percentage",
                    "Lock/unlock smart locks",
                    "Check camera feeds",
                    "Control smart plugs and switches",
                    "Check device status",
                ],
                "example_goals": [
                    "Turn off all the lights",
                    "Set the living room lights to 30%",
                    "Is the front door locked?",
                    "Turn on the bedroom fan",
                ],
            },
            "ride_services": {
                "description": "Uber and Lyft - check prices, request rides",
                "what_you_can_do": [
                    "Check current ride prices to a destination",
                    "See estimated wait times",
                    "Compare UberX vs Uber Black vs Lyft prices",
                    "Request a ride (STOPS before confirming payment)",
                ],
                "example_goals": [
                    "Check Uber prices to SFO airport",
                    "How much is a Lyft to downtown right now?",
                    "What's the wait time for an Uber?",
                    "Get me a ride to 123 Main St (will stop before booking)",
                ],
                "safety_note": "Always stops before confirming ride - returns price/ETA for your approval",
            },
            "food_delivery": {
                "description": "DoorDash, Uber Eats - browse restaurants, build orders",
                "what_you_can_do": [
                    "Search for restaurants by cuisine or name",
                    "Browse menus and prices",
                    "Check delivery times and fees",
                    "Build an order (STOPS before checkout)",
                ],
                "example_goals": [
                    "What pizza places are on DoorDash nearby?",
                    "Show me the Chipotle menu",
                    "Find Chinese food with delivery under 30 min",
                    "Order a burrito from Chipotle (will stop at checkout)",
                ],
                "safety_note": "Always stops at checkout screen - returns order summary for your approval",
            },
            "device_maintenance": {
                "description": "Phone maintenance and diagnostics",
                "what_you_can_do": [
                    "Check storage usage and free space",
                    "Get battery health and charging status",
                    "Clear app caches to free space",
                    "Check for and install app updates",
                    "View security patch level",
                    "Reboot the device (requires confirmation)",
                ],
                "example_goals": [
                    "How much storage is left on the phone?",
                    "What's the battery health?",
                    "Clear caches to free up space",
                    "Check if any apps need updates",
                    "What Android security patch is installed?",
                    "Reboot the phone",
                ],
            },
            "browser_and_search": {
                "description": "Chrome browser for web searches and navigation",
                "what_you_can_do": [
                    "Google searches",
                    "Navigate to specific websites",
                    "Read webpage content",
                    "Fill out simple forms (STOPS before submitting sensitive data)",
                ],
                "example_goals": [
                    "Google the weather forecast for tomorrow",
                    "Go to amazon.com and search for USB cables",
                    "What's the score of the Giants game?",
                    "Look up movie times at AMC nearby",
                ],
            },
            "general_apps": {
                "description": "Navigate and interact with any installed app",
                "what_you_can_do": [
                    "Open any app",
                    "Navigate menus and screens",
                    "Read displayed information",
                    "Tap buttons and enter text",
                ],
                "example_goals": [
                    "Check my email inbox",
                    "Open Settings and show battery usage",
                    "What notifications do I have?",
                    "Open Maps and search for gas stations",
                ],
            },
        },
        "supported_apps": {
            "smart_home": ["Google Home (Nest, lights, locks, cameras)"],
            "transportation": ["Uber", "Lyft", "Google Maps"],
            "food": ["DoorDash", "Uber Eats", "Grubhub", "Instacart"],
            "utilities": ["Chrome", "Settings", "Play Store", "Gmail"],
            "social": ["WhatsApp", "Instagram", "Messages"],
            "finance": ["Venmo", "Cash App (view only - stops before transactions)"],
        },
        "safety_rules": {
            "always_stops_before": [
                "Confirming any purchase or payment",
                "Booking rides, restaurants, or services",
                "Sending money or financial transactions",
                "Sending messages to people (returns draft for approval)",
                "Deleting files or data",
                "Installing or uninstalling apps",
                "Any action that can't be undone",
            ],
            "requires_explicit_confirmation": [
                "Rebooting the device",
                "Factory reset (not supported)",
                "Changing security settings",
            ],
            "how_it_works": (
                "When the automation reaches a 'point of no return', it stops and "
                "returns the current state with all details (prices, order summary, etc.) "
                "so you can review before giving the go-ahead."
            ),
        },
        "cost_and_timing": {
            "simple_read": {
                "examples": ["Check thermostat", "What's the battery level?"],
                "tokens": "5,000-8,000",
                "cost": "$0.03-0.05",
                "time": "10-15 seconds",
            },
            "simple_action": {
                "examples": ["Set thermostat to 70", "Turn off lights"],
                "tokens": "8,000-15,000",
                "cost": "$0.05-0.08",
                "time": "15-25 seconds",
            },
            "complex_navigation": {
                "examples": ["Check Uber prices to airport", "Browse DoorDash menus"],
                "tokens": "15,000-30,000",
                "cost": "$0.08-0.15",
                "time": "25-45 seconds",
            },
        },
        "tips_for_best_results": [
            "Be specific: 'Set thermostat to 68-72' is better than 'adjust temperature'",
            "Include destination for rides: 'Uber to SFO' not just 'check Uber'",
            "Mention the app if it's ambiguous: 'Check DoorDash for pizza'",
            "For reads, ask a question: 'What's the thermostat set to?'",
            "For actions, be imperative: 'Turn off the living room lights'",
        ],
        "quick_reference": {
            "thermostat": "androidPhoneTaskDo(goal='Check/Set thermostat to X-Y degrees')",
            "lights": "androidPhoneTaskDo(goal='Turn on/off [room] lights')",
            "rides": "androidPhoneTaskDo(goal='Check Uber/Lyft prices to [destination]')",
            "food": "androidPhoneTaskDo(goal='Search DoorDash for [cuisine]')",
            "maintenance": "androidPhoneTaskDo(goal='Check storage/battery/updates')",
            "browser": "androidPhoneTaskDo(goal='Google [search term]')",
        },
    }


# Keep old name as alias for backwards compatibility
async def api_get_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Alias for api_learn_action for backwards compatibility."""
    return await api_learn_action(arguments)


__all__ = [
    # Screen and basic actions (internal/advanced use)
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
    # Thermostat-specific (internal use - prefer task_do_action)
    "thermostat_set_range_action",
    "thermostat_get_status_action",
    # Audit and maintenance (internal use)
    "android_phone_audit_action",
    "update_apps_action",
    "check_security_action",
    "reboot_action",
    "get_storage_action",
    "clear_cache_action",
    "battery_health_action",
    # PRIMARY PUBLIC API (5 endpoints for ChatGPT)
    "api_learn_action",      # androidPhoneApiLearn - learn capabilities
    "task_do_action",        # androidPhoneTaskDo - start a task
    "task_get_action",       # androidPhoneTaskGet - get task status
    "task_list_action",      # androidPhoneTaskList - list tasks
    "task_cancel_action",    # androidPhoneTaskCancel - cancel a task
    # Backwards compatibility aliases
    "api_get_action",
    "do_task_action",
]
