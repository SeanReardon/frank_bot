"""
System status action: orchestration machinery health and state.

Exposes the internal workings of the jorb system:
- Switchboard (message routing)
- Message buffer (debouncing)
- Agent runner (LLM execution)
- Telegram jorb router (incoming message handling)
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def get_system_status_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Get the status of Frank Bot's orchestration machinery.

    Returns status of:
    - Switchboard: Routes incoming messages to correct jorbs
    - Message Buffer: Debounces rapid messages before processing
    - Agent Runner: Executes LLM calls for jorb conversations
    - Telegram Router: Connects Telegram messages to jorb system

    This helps answer: "Is everything awake and working?"
    """
    from config import get_settings
    from services.switchboard import get_switchboard, SWITCHBOARD_MODEL
    from services.agent_runner import AgentRunner, AGENT_MODEL
    from services.telegram_jorb_router import get_router_status
    from services.jorb_storage import JorbStorage

    settings = get_settings()

    # Switchboard status
    switchboard = get_switchboard()
    switchboard_status = {
        "configured": switchboard.is_configured,
        "model": SWITCHBOARD_MODEL,
        "description": "Routes incoming messages to the correct jorb based on sender and context",
    }

    # Agent runner status
    agent_runner = AgentRunner()
    agent_status = {
        "configured": agent_runner.is_configured,
        "model": AGENT_MODEL,
        "description": "Executes jorb conversations - decides responses, sends messages, pauses for approval",
    }

    # Telegram router status
    telegram_router = get_router_status()
    telegram_router["description"] = "Listens for Telegram messages from jorb contacts and routes them for processing"

    # Message buffer - get from telegram router or create fresh
    buffer_status = {
        "pending_messages": telegram_router.get("pending_messages", 0),
        "debounce_telegram_seconds": settings.debounce_telegram_seconds,
        "debounce_sms_seconds": settings.debounce_sms_seconds,
        "description": "Batches rapid messages together before sending to LLM",
    }

    # Jorb system stats
    storage = JorbStorage()
    open_jorbs = await storage.list_jorbs(status_filter="open")
    jorb_counts = {
        "planning": 0,
        "running": 0,
        "paused": 0,
    }
    for jorb in open_jorbs:
        if jorb.status in jorb_counts:
            jorb_counts[jorb.status] += 1

    jorbs_status = {
        "total_open": len(open_jorbs),
        "by_status": jorb_counts,
        "needs_attention": jorb_counts["paused"],
    }

    # Android phone status (via ADB)
    try:
        from actions.android_phone import android_phone_health_action
        phone_health = await android_phone_health_action()
    except Exception as exc:
        logger.warning("Failed to get phone health: %s", exc)
        phone_health = {
            "connected": False,
            "error": str(exc),
        }

    phone_status = {
        "connected": phone_health.get("connected", False),
        "device_model": phone_health.get("device_model"),
        "android_version": phone_health.get("android_version"),
        "battery_level": phone_health.get("battery_level"),
        "wifi_ssid": phone_health.get("wifi_ssid"),
        "error": phone_health.get("error"),
        "description": "Android phone connected via ADB for automation",
    }

    # Overall health
    all_configured = (
        switchboard_status["configured"]
        and agent_status["configured"]
        and telegram_router.get("telegram_configured", False)
    )

    # Build summary message
    lines = []
    if all_configured:
        lines.append("🟢 All systems operational")
    else:
        lines.append("🟡 Some systems not configured")

    lines.append("")
    lines.append(f"📡 Switchboard: {'✓' if switchboard_status['configured'] else '✗'} ({SWITCHBOARD_MODEL})")
    lines.append(f"🤖 Agent Runner: {'✓' if agent_status['configured'] else '✗'} ({AGENT_MODEL})")
    lines.append(f"✈️ Telegram Router: {'✓' if telegram_router.get('initialized') else '✗'}")
    lines.append(f"📨 Message Buffer: {buffer_status['pending_messages']} pending")
    phone_icon = "✓" if phone_status["connected"] else "✗"
    bat = phone_status.get("battery_level")
    bat_str = f" {bat}%" if bat is not None else ""
    lines.append(f"📱 Android Phone: {phone_icon}{bat_str}")
    lines.append("")
    lines.append(f"📋 Open Jorbs: {jorbs_status['total_open']} ({jorbs_status['needs_attention']} need attention)")

    return {
        "message": "\n".join(lines),
        "healthy": all_configured,
        "switchboard": switchboard_status,
        "agent_runner": agent_status,
        "telegram_router": telegram_router,
        "message_buffer": buffer_status,
        "jorbs": jorbs_status,
        "android_phone": phone_status,
    }


__all__ = ["get_system_status_action"]
