"""
Android device control actions.

Provides high-level actions for controlling an Android device via ADB,
enabling Frank to interact with mobile apps like Uber, DoorDash, etc.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from services.android_client import get_android_client

logger = logging.getLogger(__name__)


async def android_status_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Get the status of the Android device connection.
    
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


async def android_screen_action(
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


async def android_tap_action(
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


async def android_type_action(
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


async def android_swipe_action(
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


async def android_key_action(
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


async def android_launch_app_action(
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


async def android_wake_action(
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


async def android_screenshot_action(
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


async def android_find_and_tap_action(
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


__all__ = [
    "android_status_action",
    "android_screen_action",
    "android_tap_action",
    "android_type_action",
    "android_swipe_action",
    "android_key_action",
    "android_launch_app_action",
    "android_wake_action",
    "android_screenshot_action",
    "android_find_and_tap_action",
]
