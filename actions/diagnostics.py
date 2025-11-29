"""
Diagnostics action: service stats, API performance, and health info.
"""

from __future__ import annotations

import platform
import sys
from typing import Any

from services.stats import stats


async def get_diagnostics_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Get comprehensive diagnostics and performance statistics.
    
    Includes:
    - Server uptime
    - API call counts by endpoint
    - Swarm API performance (latency, success rate, bytes transferred)
    - Recent errors
    - System info
    """
    all_stats = stats.get_all_stats()
    
    # Add system info
    all_stats["system"] = {
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
    }
    
    # Build a human-readable summary message
    server = all_stats["server"]
    interactions = all_stats["interactions"]
    services = all_stats.get("services", {})
    
    lines = [
        f"🟢 Frank Bot running for {server['uptime_human']}",
        f"📊 Total API calls: {interactions['total_api_calls']}",
    ]
    
    # Service stats
    service_icons = {
        "swarm": "🐝",
        "google_calendar": "📅",
        "google_contacts": "👥",
    }
    
    for name, svc in services.items():
        icon = service_icons.get(name, "🔌")
        req = svc["requests"]
        lat = svc["latency_ms"]
        line = (
            f"{icon} {name}: {req['total']} requests "
            f"({req['success_rate']} success), "
            f"avg {lat['avg']}ms"
        )
        if lat["max"] > 0:
            line += f", max {lat['max']}ms"
        if svc.get("bytes_received", 0) > 0:
            line += f", {svc['bytes_received_human']}"
        lines.append(line)
    
    # Recent errors summary
    errors = all_stats.get("recent_errors", [])
    if errors:
        lines.append(f"⚠️ {len(errors)} recent error(s) logged")
    else:
        lines.append("✅ No recent errors")
    
    all_stats["message"] = "\n".join(lines)
    
    return all_stats


__all__ = ["get_diagnostics_action"]

