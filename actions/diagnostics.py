"""
Diagnostics action: service stats, API performance, and health info.
"""

from __future__ import annotations

import os
import platform
import sys
from typing import Any

from services.platform_info import get_platform_diagnostics
from services.stats import stats

# Git commit hash baked into Docker image at build time
GIT_COMMIT = os.environ.get("GIT_COMMIT", "unknown")
GITHUB_REPO = "SeanReardon/frank_bot"


async def get_diagnostics_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Get comprehensive diagnostics and performance statistics.
    
    Includes:
    - Server uptime
    - API call counts by endpoint
    - Swarm API performance (latency, success rate, bytes transferred)
    - Platform diagnostics (CPU, memory, network)
    - Recent errors
    - System info
    """
    all_stats = stats.get_all_stats()
    
    # Add system info
    all_stats["system"] = {
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
    }
    
    # Add build info with git commit
    commit_url = None
    if GIT_COMMIT != "unknown":
        commit_url = f"https://github.com/{GITHUB_REPO}/commit/{GIT_COMMIT}"
    all_stats["build"] = {
        "git_commit": GIT_COMMIT,
        "git_commit_short": GIT_COMMIT[:7] if GIT_COMMIT != "unknown" else "unknown",
        "git_commit_url": commit_url,
    }
    
    # Add platform diagnostics
    all_stats["platform"] = get_platform_diagnostics()
    
    # Build a human-readable summary message
    server = all_stats["server"]
    interactions = all_stats["interactions"]
    services = all_stats.get("services", {})
    plat = all_stats.get("platform", {})
    
    build = all_stats["build"]
    lines = [
        f"🟢 Frank Bot running for {server['uptime_human']}",
        f"🏷️ Build: {build['git_commit_short']}",
        f"📊 Total API calls: {interactions['total_api_calls']}",
    ]
    
    # Platform summary
    host_info = plat.get("host", {})
    mem_info = plat.get("memory", {})
    cpu_info = plat.get("cpu", {})
    net_info = plat.get("network", {})
    proc_info = plat.get("process", {})
    
    # Host uptime
    if host_info.get("uptime_human"):
        lines.append(f"🖥️ Host uptime: {host_info['uptime_human']}")
    
    # Memory
    sys_mem = mem_info.get("system", {})
    proc_mem = proc_info.get("memory_rss", {})
    if sys_mem and proc_mem:
        lines.append(
            f"💾 Memory: {proc_mem.get('human', '?')} used by Frank "
            f"/ {sys_mem.get('used_human', '?')} system "
            f"({sys_mem.get('used_percent', 0)}% of {sys_mem.get('total_human', '?')})"
        )
    
    # CPU
    cpu_snap = cpu_info.get("snapshot", {})
    load = host_info.get("load_average", {})
    if cpu_snap or load:
        cpu_parts = []
        if cpu_snap:
            cpu_parts.append(f"{cpu_snap.get('busy_percent', 0)}% busy")
        if load:
            cpu_parts.append(f"load {load.get('1min', 0):.2f}/{load.get('5min', 0):.2f}/{load.get('15min', 0):.2f}")
        lines.append(f"⚡ CPU: {', '.join(cpu_parts)}")
    
    # Network
    if net_info.get("public_ip"):
        lines.append(f"🌐 Public IP: {net_info['public_ip']}")
    
    lines.append("")  # Blank line before services
    
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

